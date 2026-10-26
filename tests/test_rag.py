"""RAG only returns references from supplied retrieval metadata."""

from pathlib import Path

import pytest

from study_agent.rag import CitationError, build_context, generate_answer
from study_agent.search import SearchHit


def hit(text: str = "Матрица — прямоугольная таблица элементов.") -> SearchHit:
    return SearchHit(
        "Алгебра",
        "algebra.pdf",
        text,
        1,
        Path("/synthetic"),
        page_number=17,
        heading="Матрицы",
        chunk_id="doc:0",
    )


def test_grounded_answer_retains_exact_snippet_and_page() -> None:
    seen = {}

    def generator(model, question, context, language):
        seen["context"] = context
        return "Матрица — таблица элементов [1]."

    result = generate_answer("local", "Что такое матрица?", [hit()], generator=generator)
    assert result.grounded
    assert result.sources[0].page_number == 17
    assert result.sources[0].excerpt in seen["context"]
    assert "/synthetic" not in seen["context"]


@pytest.mark.parametrize(
    "response",
    [
        "Нет цитат",
        "Ответ [99]",
        "Ответ [0]",
        "Факт [1].\n\nЕщё один длинный абзац с выдуманным фактом без ссылки на исходник.",
    ],
)
def test_invalid_citations_never_reach_ui(response) -> None:
    with pytest.raises(CitationError):
        generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: response)


def test_empty_context_refuses_without_calling_model() -> None:
    result = generate_answer(
        "local",
        "Цена биткоина?",
        [],
        language="ru",
        generator=lambda *a, **k: pytest.fail("must not generate"),
    )
    assert not result.grounded and result.sources == []
    assert "недостаточно" in result.answer


def test_model_can_decline_irrelevant_retrieval_without_citations() -> None:
    result = generate_answer(
        "local", "Цена биткоина?", [hit()], generator=lambda *a, **k: "INSUFFICIENT_CONTEXT"
    )
    assert not result.grounded and result.sources == []


def test_context_budget_includes_unicode_and_labels() -> None:
    context, sources = build_context([hit("абвг " * 1000)], max_bytes=500)
    assert len(context.encode("utf-8")) <= 500
    assert sources[0].excerpt in context
    assert sources[0].excerpt != "абвг " * 1000


@pytest.mark.parametrize(
    "response",
    [
        "См. [1](https://invented.example/lesson).",
        "Источник [1] https://invented.example",
        "Источник [1] file:///private/secret",
        "[1] [Документ](../forged.pdf)",
    ],
)
def test_model_cannot_invent_clickable_source_links(response) -> None:
    with pytest.raises(CitationError, match="links"):
        generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: response)


def test_only_cited_sources_are_returned_and_renumbered_together() -> None:
    from dataclasses import replace

    first = hit()
    second = replace(first, document_id="second.pdf", chunk_id="second:0", page_number=18)
    result = generate_answer(
        "local", "Вопрос?", [first, second], generator=lambda *a, **k: "Проверяемый факт [2]."
    )
    assert result.answer == "Проверяемый факт [1]."
    assert [source.document_id for source in result.sources] == ["second.pdf"]
    assert result.sources[0].page_number == 18


def test_short_definition_is_not_discarded_as_insufficient() -> None:
    result = generate_answer(
        "local",
        "Что такое TCP?",
        [hit("TCP — протокол.")],
        generator=lambda *a, **k: "TCP — протокол [1].",
    )
    assert result.grounded and result.sources[0].excerpt == "TCP — протокол."
