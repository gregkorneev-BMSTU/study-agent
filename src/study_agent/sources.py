"""Read-only access to documents in an explicitly selected local folder."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from study_agent.extractors import OCR_SUFFIXES, extract_document
from study_agent.models import ExtractedBlock

SUPPORTED_SUFFIXES = {".md", ".txt", ".docx", *OCR_SUFFIXES}


@dataclass(frozen=True)
class DocumentRef:
    """Metadata used to identify a supported file without loading its contents."""

    document_id: str
    title: str
    path: str
    size_bytes: int
    modified_at: datetime
    modified_ns: int = 0


class LocalFolderSource:
    """Enumerate and read supported local study materials."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    def list_documents(self) -> list[DocumentRef]:
        documents = []

        def raise_walk_error(error: OSError) -> None:
            raise error

        for directory, subdirs, files in os.walk(self.root, onerror=raise_walk_error):
            subdirs[:] = [name for name in subdirs if not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                if path.is_symlink() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                stat = path.stat()
                if not path.is_file():
                    continue
                relative_path = path.relative_to(self.root).as_posix()
                documents.append(
                    DocumentRef(
                        document_id=relative_path,
                        title=path.stem,
                        path=relative_path,
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        modified_ns=stat.st_mtime_ns,
                    )
                )
        return sorted(documents, key=lambda document: document.path.casefold())

    def read(self, document_id: str) -> list[ExtractedBlock]:
        """Read a listed document as structured blocks, rejecting traversal and symlink paths."""
        relative_path = Path(document_id)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("document_id must be a relative path inside the selected folder")

        path = self.root / relative_path
        if path.is_symlink() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("document_id does not identify a supported regular file")
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_relative_to(self.root) or not resolved_path.is_file():
            raise ValueError("document_id does not identify a file inside the selected folder")

        # Теперь возвращает список структурированных блоков вместо сырой строки
        return extract_document(resolved_path)
