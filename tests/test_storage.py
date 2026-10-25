"""SQLite index persistence and source isolation."""

from pathlib import Path

import pytest

from study_agent.chunking import Chunk
from study_agent.storage import IndexStorage


def _put(storage: IndexStorage, source: str, doc: str, text: str) -> None:
    storage.put_document(
        source_id=source,
        document_id=doc,
        relative_path="Лекция.txt",
        title="Лекция",
        file_format=".txt",
        size_bytes=len(text),
        modified_ns=1,
        content_hash=None,
        version="test",
        state="ready",
        warnings=[],
        chunks=[Chunk(0, text, None, None, None, "digital")],
    )


def test_persist_replace_and_remove(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite3"
    storage = IndexStorage(path)
    storage.register_source("a", str(tmp_path / "a"))
    _put(storage, "a", "a-doc", "старый термин")
    assert storage.search(["a"], "старый")

    reopened = IndexStorage(path)
    assert reopened.search(["a"], "старый")
    _put(reopened, "a", "a-doc", "новый термин")
    assert not reopened.search(["a"], "старый")
    assert reopened.search(["a"], "новый")

    reopened.remove_source("a")
    assert not reopened.search(["a"], "новый")


def test_same_filename_in_two_sources_is_independent(tmp_path: Path) -> None:
    storage = IndexStorage(tmp_path / "index.sqlite3")
    storage.register_source("a", str(tmp_path / "a"))
    storage.register_source("b", str(tmp_path / "b"))
    _put(storage, "a", "a-doc", "физика волна")
    _put(storage, "b", "b-doc", "математика интеграл")

    assert len(storage.search(["a"], "физика")) == 1
    assert not storage.search(["b"], "физика")
    assert len(storage.search(["b"], "интеграл")) == 1


def test_newer_schema_is_not_deleted(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
        db.execute("CREATE TABLE sentinel(value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('keep')")

    import pytest

    with pytest.raises(RuntimeError, match="newer"):
        IndexStorage(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM sentinel").fetchone()[0] == "keep"


def test_version_zero_migration_keeps_existing_rows(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE sources(id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, indexed_at TEXT)"
        )
        db.execute("INSERT INTO sources(id,root) VALUES ('old','/old')")
    storage = IndexStorage(path)
    assert storage.list_sources()[0]["id"] == "old"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_second_connection_reads_while_writer_transaction_is_open(tmp_path: Path) -> None:
    import sqlite3

    storage = IndexStorage(tmp_path / "index.sqlite3")
    storage.register_source("a", str(tmp_path / "a"))
    with storage.connect() as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE sources SET indexed_at='now' WHERE id='a'")
        with storage.connect() as reader:
            assert reader.execute("SELECT id FROM sources").fetchone()[0] == "a"
        writer.rollback()
    with sqlite3.connect(storage.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_chunk_replacement_rolls_back_previous_text(tmp_path: Path) -> None:
    import sqlite3

    storage = IndexStorage(tmp_path / "index.sqlite3")
    storage.register_source("a", str(tmp_path / "a"))
    _put(storage, "a", "a-doc", "durable text")
    with pytest.raises(sqlite3.IntegrityError):
        storage.put_document(
            source_id="a",
            document_id="a-doc",
            relative_path="Лекция.txt",
            title="Лекция",
            file_format=".txt",
            size_bytes=3,
            modified_ns=2,
            content_hash=None,
            version="test",
            state="ready",
            warnings=[],
            chunks=[
                Chunk(0, "replacement", None, None, None, "digital"),
                Chunk(0, "duplicate", None, None, None, "digital"),
            ],
        )
    assert storage.search(["a"], "durable")
    assert not storage.search(["a"], "replacement")


@pytest.mark.skipif(__import__("os").name == "nt", reason="SIGKILL is POSIX only")
def test_killed_writer_leaves_complete_document(tmp_path: Path) -> None:
    import subprocess
    import sys

    path = tmp_path / "index.sqlite3"
    storage = IndexStorage(path)
    storage.register_source("a", str(tmp_path / "a"))
    _put(storage, "a", "a-doc", "durable text")
    code = """
import sqlite3, sys, time
connection = sqlite3.connect(sys.argv[1], isolation_level=None)
connection.execute('PRAGMA foreign_keys=ON')
connection.execute('BEGIN IMMEDIATE')
connection.execute("DELETE FROM chunks WHERE document_id='a-doc'")
print('ready', flush=True)
time.sleep(30)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert IndexStorage(path).search(["a"], "durable")
    with storage.connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
