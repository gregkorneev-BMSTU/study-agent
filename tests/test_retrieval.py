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


def test_similarity_threshold_filters_semantic_candidates(tmp_path: Path) -> None:
    storage, key, embedder = corpus(tmp_path)
    found = retrieve(
        storage, [key], "таблица чисел", mode="semantic", embedder=embedder,
        min_similarity=0.99,
    )
    assert [hit.document_id for hit in found.hits] == ["algebra.md"]


def test_default_threshold_rejects_weak_greeting_match(tmp_path: Path) -> None:
    storage, key, _ = corpus(tmp_path)

    class WeakMatchEmbedder(SemanticEmbedder):
        profile = EmbeddingProfile("weak-match", "v1", 3)

        def embed_documents(self, inputs: list[str]) -> list[list[float]]:
            return [[0.5, 0.8660254, 0] for _ in inputs]

        def embed_query(self, question: str) -> list[float]:
            return [1, 0, 0]

    embedder = WeakMatchEmbedder()
    EmbeddingIndexer(storage, embedder).sync_sources([key])
    default_result = retrieve(storage, [key], "привет", mode="semantic", embedder=embedder)
    lower_result = retrieve(
        storage, [key], "привет", mode="semantic", embedder=embedder, min_similarity=0.35
    )
    assert default_result.hits == []
    assert lower_result.hits


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


def test_groups_all_matches_by_file_and_preserves_excerpts() -> None:
    from study_agent.retrieval import _unique
    from study_agent.search import SearchHit

    root = Path("/synthetic")
    hits = [
        SearchHit("A", "a.md", "Первый фрагмент", 9, root, heading="Таблица", chunk_id="1"),
        SearchHit("A", "a.md", "Второй фрагмент", 8, root, heading="Таблица", chunk_id="2"),
        SearchHit("A", "a.md", "Другой раздел", 7, root, heading="Примеры", chunk_id="3"),
        SearchHit("B", "b.md", "Первый фрагмент", 6, root, heading="Таблица", chunk_id="4"),
        SearchHit("PDF", "a.pdf", "Страница один", 5, root, page_number=1, chunk_id="5"),
        SearchHit("PDF", "a.pdf", "Страница два", 4, root, page_number=2, chunk_id="6"),
    ]
    found = _unique(hits, 8)
    assert [hit.chunk_id for hit in found] == ["1", "4", "5"]
    assert found[0].related_count == 2
    assert found[0].matched_excerpts == ["Первый фрагмент", "Второй фрагмент", "Другой раздел"]
    assert found[2].related_count == 1


def test_math_group_keeps_precise_formula_with_original_provenance() -> None:
    from study_agent.retrieval import _unique
    from study_agent.search import SearchHit

    root = Path("/synthetic")
    original = r"Заголовок: $$\int \sqrt{x} dx = F(x)+C$$" + "\nИсточник /invented/file"
    hits = [
        SearchHit(
            "A",
            "notes.md",
            r"$$\int \sqrt{dx} = x+C$$",
            10,
            root,
            heading="Интегралы",
            marker="line:8",
            chunk_id="bad",
        ),
        SearchHit(
            "A",
            "notes.md",
            original,
            8,
            root,
            heading="Интегралы",
            marker="line:12",
            chunk_id="good",
        ),
        SearchHit(
            "A",
            "notes.md",
            r"$$\int \sin x dx = F(x)$$",
            6,
            root,
            heading="Интегралы",
            marker="line:15",
            chunk_id="sin",
        ),
    ]
    found = _unique(hits, 8, "интеграл корня из x")
    assert len(found) == 1
    hit = found[0]
    assert hit.excerpt == r"$$\int \sqrt{x} dx = F(x)+C$$"
    assert hit.excerpt in original
    assert hit.related_count == 0 and hit.quality_warnings == []
    assert (hit.document_id, hit.marker, hit.chunk_id) == ("notes.md", "line:12", "good")


def test_suspect_only_source_is_retained_with_warning() -> None:
    from study_agent.retrieval import _unique
    from study_agent.search import SearchHit

    hit = SearchHit("OCR", "a.md", r"$$\int \sqrt{dx} = x$$", 1, Path("/synthetic"))
    found = _unique([hit], 8, "интеграл корня из x")
    assert len(found) == 1
    assert found[0].quality_warnings == ["formula_suspect"]


def test_semantic_math_table_uses_saved_text_and_keeps_other_document(tmp_path: Path) -> None:
    root = tmp_path / "notes"
    root.mkdir()
    expected = r"$$\int \sqrt{x} dx = \frac{2}{3}x^{3/2}+C$$"
    (root / "table.md").write_text(
        "# Интегралы\n" + r"$$\int \sqrt{x^n} dx = F(x)$$" + "\n\n" + expected,
        encoding="utf-8",
    )
    (root / "other.md").write_text(
        "# Метод\nИнтеграл корня из x объясняется степенным правилом", encoding="utf-8"
    )
    storage = IndexStorage(tmp_path / "index.sqlite3")
    DocumentIndexer(storage).sync_source(LocalFolderSource(root))

    class MathEmbedder(SemanticEmbedder):
        def embed_documents(self, inputs: list[str]) -> list[list[float]]:
            return [[1, 0, 0] for _ in inputs]

    embedder = MathEmbedder()
    key = source_id(root)
    EmbeddingIndexer(storage, embedder).sync_sources([key])
    # Search relies exclusively on the saved index, not live source extraction.
    (root / "table.md").unlink()
    result = retrieve(storage, [key], "интеграл корня из x", mode="semantic", embedder=embedder)
    assert result.hits[0].excerpt == expected
    assert {hit.document_id for hit in result.hits} == {"table.md", "other.md"}


def test_math_signature_filters_conflicting_sections_with_equal_vectors(tmp_path: Path) -> None:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "table.md").write_text(
        "# Корень\n"
        + r"$$\int \sqrt{x} dx=F(x)$$"
        + "\n\n"
        + "# Синус\n"
        + r"$$\int \sin x dx=G(x)$$"
        + "\n\n"
        + "# Обратный корень\n"
        + r"$$\int \frac{dx}{\sqrt{x}}=H(x)$$"
        + "\n\n"
        + "# Корень степени\n"
        + r"$$\int \sqrt{x^n} dx=K(x)$$",
        encoding="utf-8",
    )
    storage = IndexStorage(tmp_path / "index.sqlite3")
    DocumentIndexer(storage).sync_source(LocalFolderSource(root))

    class EqualEmbedder(SemanticEmbedder):
        def embed_documents(self, inputs: list[str]) -> list[list[float]]:
            return [[1, 0, 0] for _ in inputs]

    embedder = EqualEmbedder()
    key = source_id(root)
    EmbeddingIndexer(storage, embedder).sync_sources([key])
    result = retrieve(storage, [key], "интеграл корня из x", mode="semantic", embedder=embedder)
    assert [hit.heading for hit in result.hits] == ["Корень"]
    general = retrieve(
        storage, [key], "таблица основных интегралов", mode="semantic", embedder=embedder
    )
    assert len(general.hits) == 1
    assert len(general.hits[0].matched_excerpts) == 4
    assert len(general.hits[0].context_excerpts) >= 1


def test_precise_math_gate_retains_supporting_prose_but_drops_unrelated_document() -> None:
    from study_agent.retrieval import _unique
    from study_agent.search import SearchHit

    root = Path("/synthetic")
    hits = [
        SearchHit("Matrix", "matrix.md", "Матрица: независимый документ", 10, root),
        SearchHit(
            "Guide", "guide.md", "Интеграл корня из x объясняется степенным правилом", 9, root
        ),
        SearchHit("Formula", "formula.md", r"$$\int \sqrt{x} dx=F(x)$$", 8, root),
        SearchHit(
            "Wrong",
            "code.md",
            "Неверный пример:\n```latex\n" + r"$$\int \sqrt{x} dx=123$$" + "\n```",
            7,
            root,
        ),
    ]
    found = _unique(hits, 8, "интеграл корня из x")
    assert [hit.document_id for hit in found] == ["formula.md", "guide.md"]
    # The narrow gate is only enabled after a strong formula match.
    assert [hit.document_id for hit in _unique(hits[:2], 8, "интеграл корня из x")] == [
        "matrix.md",
        "guide.md",
    ]


def test_clean_sibling_replaces_corrupt_representative_without_reordering_groups() -> None:
    from study_agent.retrieval import _unique
    from study_agent.search import SearchHit

    root = Path("/synthetic")
    hits = [
        SearchHit("Bad", "a.md", r"\frac{x}{y", 10, root, heading="Матрицы", chunk_id="bad"),
        SearchHit("Other", "b.md", "Другой материал", 9, root, heading="Иное"),
        SearchHit(
            "Good",
            "a.md",
            "Матрица — прямоугольная таблица",
            8,
            root,
            heading="Матрицы",
            chunk_id="good",
        ),
        SearchHit(
            "Sibling",
            "a.md",
            "Матрица: ещё один хороший фрагмент",
            7,
            root,
            heading="Матрицы",
            chunk_id="sibling",
        ),
    ]
    found = _unique(hits, 8, "матрица")
    assert [hit.document_id for hit in found] == ["a.md", "b.md"]
    assert found[0].chunk_id == "good"
    assert found[0].related_count == 2
    assert found[0].quality_warnings == []


def test_focused_math_preserves_complete_chunk_for_display() -> None:
    from study_agent.retrieval import _unique, hit_value
    from study_agent.search import SearchHit

    original = (
        "# Интегралы\n\n$$\\int \\sqrt{x} dx = \\frac{2}{3}x^{3/2}+C$$"
        "\n\nДругая часть чанка."
    )
    hit = SearchHit("Lecture", "lecture.md", original, 10, Path("/synthetic"))
    result = _unique([hit], 8, "интеграл корня из x")[0]
    assert result.full_excerpt == original
    assert result.excerpt != original
    assert result.excerpt in original
    assert hit_value(result)["full_excerpt"] == original
