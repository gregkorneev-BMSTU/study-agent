"""Retrieval ranking, isolation, cache state and provenance without model downloads."""

from pathlib import Path

import pytest

from study_agent.embeddings import EmbeddingIndexer, EmbeddingProfile
from study_agent.indexer import DocumentIndexer, source_id
from study_agent.retrieval import retrieve
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


class SemanticEmbedder:
    profile = EmbeddingProfile("synthetic", "v1", 3)

    def embed_documents(self, inputs: list[str]) -> list[list[float]]:
        return [[1, 0, 0] if "Матрица" in text else [0, 1, 0] for text in inputs]

    def embed_query(self, question: str) -> list[float]:
        return [0, 0, 1] if "погода" in question else [1, 0, 0]


def corpus(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "algebra.md").write_text(
        "# Алгебра\nМатрица — прямоугольный массив элементов, расположенных по строкам и столбцам.",
        encoding="utf-8",
    )
    (root / "physics.md").write_text(
        "# Физика\nТеплопроводность — перенос энергии от горячего тела к холодному.",
        encoding="utf-8",
    )
    storage = IndexStorage(tmp_path / "index.sqlite3")
    DocumentIndexer(storage).sync_source(LocalFolderSource(root))
    embedder = SemanticEmbedder()
    EmbeddingIndexer(storage, embedder).sync_sources([source_id(root)])
    return storage, source_id(root), embedder


def test_semantic_finds_synonym_without_word_matches(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    assert not retrieve(storage, [key], "таблица чисел").hits
    embedder.embed_documents = lambda _: pytest.fail("search must not embed documents")
    found = retrieve(storage, [key], "таблица чисел", mode="semantic", embedder=embedder)
    assert [hit.document_id for hit in found.hits] == ["algebra.md"]
    assert found.hits[0].heading == "Алгебра"
    assert found.hits[0].chunk_id and found.hits[0].marker == "line:1"
    assert not found.embedding_pending


def test_hybrid_retains_exact_terms_and_semantic_candidates(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    found = retrieve(storage, [key], "Теплопроводность", mode="hybrid", embedder=embedder)
    assert {hit.document_id for hit in found.hits} == {"algebra.md", "physics.md"}
    assert all(isinstance(hit.score, int) for hit in found.hits)
    pure_vector = retrieve(
        storage, [key], "Теплопроводность", mode="hybrid", embedder=embedder, lexical_weight=0
    )
    assert [hit.document_id for hit in pure_vector.hits] == ["algebra.md"]


def test_no_false_sources_when_semantically_unrelated(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    assert not retrieve(storage, [key], "погода", mode="semantic", embedder=embedder).hits
    assert not retrieve(
        storage, ["other"], "таблица чисел", mode="semantic", embedder=embedder
    ).hits


def test_missing_vectors_mark_index_pending_without_runtime_call(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    with storage.connect() as db:
        db.execute("DELETE FROM chunk_embeddings")
    embedder.embed_query = lambda _: pytest.fail("no vectors, no query inference")
    result = retrieve(storage, [key], "таблица чисел", mode="semantic", embedder=embedder)
    assert result.embedding_pending and result.hits == []
    lexical = retrieve(storage, [key], "Матрица", mode="hybrid", embedder=embedder)
    assert lexical.embedding_pending and len(lexical.hits) == 1


def test_stale_vectors_are_not_used_after_update(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    with storage.connect() as db:
        db.execute("UPDATE chunks SET text='Новый материал' WHERE heading='Алгебра'")
    result = retrieve(storage, [key], "таблица чисел", mode="semantic", embedder=embedder)
    assert result.hits == [] and result.embedding_pending


def test_invalid_mode_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode"):
        retrieve(IndexStorage(tmp_path / "index.sqlite3"), [], "query", mode="unknown")
