from pathlib import Path

from study_agent import storage, ui


def test_search_indexes_new_qt_source_before_query(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "default_database_path", lambda: tmp_path / "index.sqlite3")
    root = tmp_path / "notes"
    root.mkdir()
    (root / "lecture.txt").write_text("Алгоритмы поиска", encoding="utf-8")

    hits, warnings = ui._index_and_search([root], "алгоритмы")

    assert [hit.document_id for hit in hits] == ["lecture.txt"]
    assert warnings == []
