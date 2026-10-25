from pathlib import Path

from study_agent.indexer import DocumentIndexer
from study_agent.search import search_sources
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


def test_search_ranks_local_files_and_returns_matching_excerpt(tmp_path: Path) -> None:
    (tmp_path / "weak.txt").write_text("Слово запрос встречается один раз.", encoding="utf-8")
    (tmp_path / "strong.md").write_text(
        "# Алгоритм\nЗапрос содержит алгоритм. Алгоритм работает по шагам.", encoding="utf-8"
    )

    source = LocalFolderSource(tmp_path)
    storage = IndexStorage(tmp_path.parent / "index.sqlite3")
    DocumentIndexer(storage).sync_source(source)
    hits = search_sources([source], "алгоритм запрос", storage=storage)

    assert [hit.document_id for hit in hits] == ["strong.md", "weak.txt"]
    assert "Алгоритм" in hits[0].excerpt


def test_search_returns_empty_for_nonmatching_query(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("Материал о графах.", encoding="utf-8")

    source = LocalFolderSource(tmp_path)
    storage = IndexStorage(tmp_path.parent / "index.sqlite3")
    DocumentIndexer(storage).sync_source(source)
    assert search_sources([source], "космос", storage=storage) == []


def test_hits_keep_their_source_when_roots_contain_the_same_relative_path(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "notes.txt").write_text("Алгоритм первый.", encoding="utf-8")
    (second / "notes.txt").write_text("Алгоритм второй.", encoding="utf-8")

    sources = [LocalFolderSource(first), LocalFolderSource(second)]
    storage = IndexStorage(tmp_path / "index.sqlite3")
    for source in sources:
        DocumentIndexer(storage).sync_source(source)
    hits = search_sources(sources, "алгоритм", storage=storage)

    assert {hit.source_root for hit in hits} == {first, second}
