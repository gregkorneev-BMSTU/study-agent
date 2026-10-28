"""Incremental indexing of user-selected local folders."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event

from study_agent.chunking import CHUNK_VERSION, chunk_blocks
from study_agent.extractors import PDF_EXTRACTION_VERSION
from study_agent.markdown import MARKDOWN_VERSION
from study_agent.sources import DocumentRef, LocalFolderSource
from study_agent.storage import IndexStorage

INDEX_VERSION = f"extract-1:chunk-{CHUNK_VERSION}"
ProgressCallback = Callable[[dict], None]


def source_id(root: Path) -> str:
    return hashlib.sha256(os.fsencode(str(root.resolve()))).hexdigest()


def document_id(source_key: str, relative_path: str) -> str:
    return hashlib.sha256(f"{source_key}\0{relative_path}".encode()).hexdigest()


@dataclass
class IndexReport:
    source_id: str
    total: int = 0
    indexed: int = 0
    partial: int = 0
    skipped: int = 0
    failed: int = 0
    removed: int = 0
    cancelled: bool = False
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class IndexBusyError(RuntimeError):
    """Another process is already indexing this library."""


class _WriterLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = None

    def __enter__(self) -> _WriterLock:
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                self.file.write(b"0")
                self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise IndexBusyError("Another Study Agent process is indexing this library") from error
        return self

    def __exit__(self, *_: object) -> None:
        if self.file is not None:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()


class DocumentIndexer:
    def __init__(self, storage: IndexStorage) -> None:
        self.storage = storage

    def sync_source(
        self,
        source: LocalFolderSource,
        progress_callback: ProgressCallback | None = None,
        cancel_token: Event | None = None,
        *,
        verify_hash: bool = False,
    ) -> IndexReport:
        key = source_id(source.root)
        report = IndexReport(key)
        with _WriterLock(self.storage.path.with_suffix(".lock")):
            # A failed or inaccessible traversal must never erase the saved library.
            if not source.root.is_dir():
                raise FileNotFoundError("Source folder is unavailable")
            scan_errors: list[tuple[str, str]] = []
            documents = source.list_documents(scan_errors)
            report.total = len(documents) + len(scan_errors)
            self.storage.register_source(key, str(source.root))
            seen = {doc.path for doc in documents} | {path for path, _ in scan_errors}
            for path, code in scan_errors:
                report.failed += 1
                report.errors.append({"document_id": path, "code": code})
                self.storage.record_error(
                    key,
                    document_id(key, path),
                    path,
                    Path(path).stem,
                    Path(path).suffix.lower(),
                    0,
                    0,
                    INDEX_VERSION,
                    code,
                )
            self._progress(report, progress_callback, "scanning")
            for doc in documents:
                if cancel_token is not None and cancel_token.is_set():
                    report.cancelled = True
                    break
                self._index_document(source, key, doc, report, verify_hash)
                self._progress(report, progress_callback, "indexing")
            if not report.cancelled:
                # Recheck root accessibility before deleting stale records.
                if not source.root.is_dir():
                    raise FileNotFoundError("Source folder became unavailable")
                report.removed = self.storage.delete_missing(key, seen)
                self.storage.mark_source_indexed(key)
            self._progress(
                report, progress_callback, "cancelled" if report.cancelled else "complete"
            )
        return report

    index_source = sync_source

    def _index_document(
        self,
        source: LocalFolderSource,
        key: str,
        doc: DocumentRef,
        report: IndexReport,
        verify_hash: bool,
    ) -> None:
        doc_key = document_id(key, doc.path)
        suffix = Path(doc.path).suffix.lower()
        if suffix == ".md":
            processing_version = f"{INDEX_VERSION}:md-{MARKDOWN_VERSION}"
        elif suffix == ".pdf":
            processing_version = f"{INDEX_VERSION}:pdf-{PDF_EXTRACTION_VERSION}"
        else:
            processing_version = INDEX_VERSION
        previous = self.storage.get_document(key, doc.path)
        digest = None
        try:
            if verify_hash:
                digest = self._hash_file(source, doc.path)
            if (
                previous is not None
                and previous["state"] == "ready"
                and previous["size_bytes"] == doc.size_bytes
                and previous["modified_ns"] == doc.modified_ns
                and previous["version"] == processing_version
                and (not verify_hash or previous["content_hash"] == digest)
            ):
                report.skipped += 1
                return
            blocks = source.read(doc.document_id)
            chunks = chunk_blocks(blocks)
            warnings = [
                {
                    "document_id": doc.path,
                    "title": doc.title,
                    "code": "ocr_failed"
                    if block.extraction_type == "ocr"
                    else "document_extraction_failed",
                    "page_number": block.page_number,
                }
                for block in blocks
                if block.warnings
            ]
            state = "partial" if warnings else "ready"
            # Do not accept a file that changed during OCR as current.
            actual = (source.root / doc.path).stat()
            if actual.st_size != doc.size_bytes or actual.st_mtime_ns != doc.modified_ns:
                raise OSError("Document changed during extraction")
            self.storage.put_document(
                source_id=key,
                document_id=doc_key,
                relative_path=doc.path,
                title=doc.title,
                file_format=Path(doc.path).suffix.lower(),
                size_bytes=doc.size_bytes,
                modified_ns=doc.modified_ns,
                content_hash=digest,
                version=processing_version,
                state=state,
                warnings=warnings,
                chunks=chunks,
            )
            if state == "partial":
                report.partial += 1
            else:
                report.indexed += 1
        except Exception as error:
            code = "document_extraction_failed"
            if isinstance(error, FileNotFoundError):
                code = "document_disappeared"
            elif isinstance(error, PermissionError):
                code = "permission_denied"
            elif isinstance(error, OSError) and "changed" in str(error):
                code = "document_changed"
            report.failed += 1
            report.errors.append({"document_id": doc.path, "code": code})
            self.storage.record_error(
                key,
                doc_key,
                doc.path,
                doc.title,
                Path(doc.path).suffix.lower(),
                doc.size_bytes,
                doc.modified_ns,
                processing_version,
                code,
            )

    @staticmethod
    def _hash_file(source: LocalFolderSource, relative_path: str) -> str:
        # Only used on explicit verification, never on a search request.
        path = source.root / relative_path
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(source.root):
            raise ValueError("Document is outside selected source")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _progress(report: IndexReport, callback: ProgressCallback | None, phase: str) -> None:
        if callback is not None:
            callback(
                {
                    "phase": phase,
                    "current": report.indexed + report.partial + report.skipped + report.failed,
                    "total": report.total,
                    "indexed": report.indexed,
                    "partial": report.partial,
                    "skipped": report.skipped,
                    "failed": report.failed,
                }
            )

    def remove_source(self, key: str) -> None:
        with _WriterLock(self.storage.path.with_suffix(".lock")):
            self.storage.remove_source(key)

    def get_index_status(self, key: str) -> dict:
        with self.storage.connect() as db:
            source = db.execute("SELECT indexed_at FROM sources WHERE id=?", (key,)).fetchone()
            row = db.execute(
                """
                SELECT count(*) AS documents,
                       sum(state='ready') AS ready,
                       sum(state='partial') AS partial,
                       sum(state IN ('error','retry')) AS failed
                FROM documents WHERE source_id=?
            """,
                (key,),
            ).fetchone()
            chunks = db.execute(
                """
                SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE d.source_id=?
            """,
                (key,),
            ).fetchone()[0]
        return {
            "source_id": key,
            "documents": row["documents"],
            "ready": row["ready"] or 0,
            "partial": row["partial"] or 0,
            "failed": row["failed"] or 0,
            "chunks": chunks,
            "last_indexed_at": source["indexed_at"] if source is not None else None,
            "issues": self.storage.list_warnings([key]),
        }
