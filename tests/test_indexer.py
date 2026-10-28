"""Incremental indexing against synthetic local files only."""

from pathlib import Path
from threading import Event

import pytest

from study_agent.indexer import DocumentIndexer, source_id
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


def _setup(tmp_path: Path) -> tuple[Path, LocalFolderSource, IndexStorage, DocumentIndexer]:
    root = tmp_path / "materials"
    root.mkdir()
    source = LocalFolderSource(root)
    storage = IndexStorage(tmp_path / "index.sqlite3")
    return root, source, storage, DocumentIndexer(storage)


def test_initial_incremental_change_add_delete_and_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    (root / "one.txt").write_text("alpha original", encoding="utf-8")
    (root / "two.md").write_text("beta original", encoding="utf-8")
    read = source.read
    calls: list[str] = []

    def counted(document_id: str):
        calls.append(document_id)
        return read(document_id)

    monkeypatch.setattr(source, "read", counted)
    first = indexer.sync_source(source)
    assert first.indexed == 2
    assert len(calls) == 2
    status = indexer.get_index_status(source_id(root))
    assert status["chunks"] == 2
    assert status["last_indexed_at"]

    second = indexer.sync_source(source)
    assert second.skipped == 2
    assert len(calls) == 2

    (root / "one.txt").write_text("gamma replacement with different length", encoding="utf-8")
    (root / "three.txt").write_text("delta added", encoding="utf-8")
    third = indexer.sync_source(source)
    assert third.indexed == 2 and third.skipped == 1
    assert len(calls) == 4
    assert not storage.search([source_id(root)], "alpha")
    assert storage.search([source_id(root)], "gamma")
    assert storage.search([source_id(root)], "delta")

    (root / "two.md").unlink()
    fourth = indexer.sync_source(source)
    assert fourth.removed == 1
    assert not storage.search([source_id(root)], "beta")

    reopened = IndexStorage(tmp_path / "index.sqlite3")
    assert reopened.search([source_id(root)], "gamma")
    assert DocumentIndexer(reopened).sync_source(source).skipped == 2
    assert len(calls) == 4


def test_search_uses_index_without_reading_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    (root / "lesson.txt").write_text("квантовая механика", encoding="utf-8")
    indexer.sync_source(source)

    def forbidden(_: str):
        raise AssertionError("search must not reextract documents")

    monkeypatch.setattr(source, "read", forbidden)
    assert storage.search([source_id(root)], "квантовая")


def test_failed_document_does_not_stop_others_or_erase_old_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    (root / "bad.txt").write_text("durable old text", encoding="utf-8")
    indexer.sync_source(source)
    (root / "bad.txt").write_text("changed content longer", encoding="utf-8")
    (root / "good.txt").write_text("success token", encoding="utf-8")
    read = source.read

    def sometimes_fails(document_id: str):
        if document_id == "bad.txt":
            raise ValueError("synthetic extractor failure")
        return read(document_id)

    monkeypatch.setattr(source, "read", sometimes_fails)
    report = indexer.sync_source(source)
    assert report.failed == 1 and report.indexed == 1
    assert storage.search([source_id(root)], "durable")
    assert storage.search([source_id(root)], "success")
    assert storage.list_warnings([source_id(root)])
    reopened = IndexStorage(tmp_path / "index.sqlite3")
    issues = DocumentIndexer(reopened).get_index_status(source_id(root))["issues"]
    assert issues == [
        {
            "document_id": "bad.txt",
            "title": "bad",
            "code": "document_extraction_failed",
            "page_number": None,
        }
    ]


def test_cancel_preserves_index_and_resume(tmp_path: Path) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    for index in range(3):
        (root / f"{index}.txt").write_text(f"token{index} text", encoding="utf-8")
    token = Event()

    def cancel_after_first(progress: dict) -> None:
        if progress["current"] == 1:
            token.set()

    report = indexer.sync_source(source, cancel_after_first, token)
    assert report.cancelled and report.indexed == 1
    assert indexer.get_index_status(source_id(root))["documents"] == 1
    resumed = indexer.sync_source(source)
    assert resumed.skipped == 1 and resumed.indexed == 2
    assert indexer.get_index_status(source_id(root))["documents"] == 3


def test_unavailable_source_does_not_delete_index(tmp_path: Path) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    (root / "lesson.txt").write_text("persistent text", encoding="utf-8")
    indexer.sync_source(source)
    root.rename(tmp_path / "detached")

    with pytest.raises(FileNotFoundError):
        indexer.sync_source(source)
    assert storage.search([source_id(root)], "persistent")


def test_parallel_indexer_reports_busy(tmp_path: Path) -> None:
    from study_agent.indexer import IndexBusyError, _WriterLock

    root, source, _, indexer = _setup(tmp_path)
    (root / "lesson.txt").write_text("one", encoding="utf-8")
    with _WriterLock(indexer.storage.path.with_suffix(".lock")):
        with pytest.raises(IndexBusyError):
            indexer.sync_source(source)


def test_structured_pdf_page_and_ocr_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from study_agent.models import ExtractedBlock

    root, source, storage, indexer = _setup(tmp_path)
    (root / "page.pdf").write_bytes(b"synthetic")
    monkeypatch.setattr(
        source,
        "read",
        lambda _: [
            ExtractedBlock("", "pdf", "ocr", page_number=1, warnings=["missing OCR"]),
            ExtractedBlock("alpha searchable", "pdf", "digital", page_number=2),
        ],
    )
    report = indexer.sync_source(source)
    assert report.partial == 1
    row = storage.search([source_id(root)], "alpha")[0]
    assert row["page_number"] == 2
    assert storage.list_warnings([source_id(root)])[0]["page_number"] == 1


@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError])
def test_file_stat_failure_does_not_stop_scan_or_delete_saved_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[OSError]
) -> None:
    root, source, storage, indexer = _setup(tmp_path)
    bad = root / "bad.txt"
    bad.write_text("durable original", encoding="utf-8")
    indexer.sync_source(source)
    (root / "good.txt").write_text("new searchable", encoding="utf-8")
    actual_stat = Path.stat

    def failing_stat(path: Path, *args: object, **kwargs: object):
        if path == bad:
            raise error_type("file unavailable")
        return actual_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing_stat)
    assert [doc.path for doc in source.list_documents()] == ["good.txt"]
    report = indexer.sync_source(source)
    assert report.failed == 1 and report.indexed == 1
    assert report.errors[0]["document_id"] == "bad.txt"
    assert storage.search([source_id(root)], "durable")
    assert storage.search([source_id(root)], "searchable")
    assert storage.list_warnings([source_id(root)])[0]["code"] == report.errors[0]["code"]


def test_markdown_processing_upgrade_reextracts_only_markdown(tmp_path: Path, monkeypatch) -> None:
    from study_agent.indexer import INDEX_VERSION

    root, source, storage, indexer = _setup(tmp_path)
    (root / "notes.md").write_text("# Раздел\nФормула $$x^2$$", encoding="utf-8")
    (root / "notes.txt").write_text("Обычный текст", encoding="utf-8")
    indexer.sync_source(source)
    # Simulate a pre-math Markdown index while keeping other formats current.
    with storage.connect() as db:
        db.execute("UPDATE documents SET version=? WHERE format='.md'", (INDEX_VERSION,))
    reads = []
    original = source.read

    def read(document_id):
        reads.append(document_id)
        return original(document_id)

    monkeypatch.setattr(source, "read", read)
    report = indexer.sync_source(source)
    assert reads == ["notes.md"]
    assert report.indexed == 1 and report.skipped == 1
