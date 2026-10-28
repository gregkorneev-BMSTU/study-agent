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


def test_structural_intro_and_cited_formula_list_are_valid() -> None:
    answer = (
        "Вот таблица интегралов из материала:\n\n"
        "* $\\int 1\\,dx=x+C$ [SOURCE 1]\n"
        "* $\\int x\\,dx=\\frac{x^2}{2}+C$ [SOURCE 1]"
    )
    result = generate_answer(
        "local", "Покажи таблицу интегралов.", [hit()], generator=lambda *a, **k: answer
    )
    assert result.grounded
    assert result.answer.count("[1]") == 2
    assert result.answer.startswith("Вот таблица интегралов из материала:")


def test_uncited_factual_claim_ending_with_colon_is_still_rejected() -> None:
    with pytest.raises(CitationError) as failure:
        generate_answer(
            "local", "Вопрос?", [hit()],
            generator=lambda *a, **k: (
                "Полученная математическая формула из этого расчёта неверна:\n\n"
                "Подтверждённое утверждение из источника [1]."
            ),
        )
    assert failure.value.reason == "uncited_paragraph"


def test_distinct_source_label_is_normalized_for_display() -> None:
    result = generate_answer(
        "local", "Что такое матрица?", [hit()],
        generator=lambda *a, **k: "Матрица — таблица [SOURCE 1].",
    )
    assert result.answer == "Матрица — таблица [1]."
    assert result.grounded


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


def test_context_omits_ocr_formula_numbers_from_prompt_only() -> None:
    numbered = r"$$\textcircled{9} \int \frac{dx}{x}=\ln|x|+C$$"
    context, sources = build_context([hit(numbered)])
    assert r"\textcircled{9}" not in context
    assert r"\int \frac{dx}{x}" in context
    assert sources[0].excerpt == numbered


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


@pytest.mark.parametrize(
    ("response", "reason", "extra"),
    [
        ("Ответ без ссылок", "missing_citations", {}),
        ("Ответ [9]", "unknown_source", {"invalid_sources": [9]}),
        (
            "Факт [1].\n\nОтдельный содержательный абзац без указания проверяемого источника.",
            "uncited_paragraph",
            {"paragraph_index": 2},
        ),
        ("См. [1](https://invalid.example)", "generated_links", {}),
    ],
)
def test_error_has_safe_specific_reason_and_details(response, reason, extra) -> None:
    with pytest.raises(CitationError) as failure:
        generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: response)
    error = failure.value
    assert error.reason == reason
    assert error.details == {"source_count": 1, **extra}
    assert response not in error.message("ru")
    assert response not in str(error.details)
    assert error.message("en") != error.message("ru")
    assert error.action("ru")


def test_display_equation_inherits_adjacent_explanation_citation() -> None:
    text = "Интеграл из источника записывается следующим образом [1]:\n\n" + (
        r"\[\int\sqrt{x}\,dx=\frac{2}{3}x^{3/2}+C\]"
    )
    result = generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: text)
    assert result.grounded and result.answer == text


def test_mathematical_brackets_are_not_source_numbers() -> None:
    text = r"Значение $x[99]$ используется в записи [1]."
    result = generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: text)
    assert result.grounded and "$x[99]$" in result.answer


def test_citation_groups_are_valid_and_renumber_with_metadata() -> None:
    from dataclasses import replace

    first = hit()
    second = replace(first, chunk_id="doc:1", document_id="second.pdf")
    result = generate_answer(
        "local",
        "Вопрос?",
        [first, second],
        generator=lambda *a, **k: "Данные из двух источников [2, 1].",
    )
    assert result.answer == "Данные из двух источников [1], [2]."
    assert [source.document_id for source in result.sources] == ["second.pdf", "algebra.pdf"]


def test_suspect_source_is_not_forwarded_to_model() -> None:
    damaged = hit(r"$$\int \sqrt{dx}=x+C$$")
    with pytest.raises(CitationError) as failure:
        generate_answer(
            "local",
            "Вопрос?",
            [damaged],
            generator=lambda *a, **k: pytest.fail("damaged formula must not be sent"),
        )
    assert failure.value.reason == "source_quality"
    assert failure.value.details == {"source_count": 0, "warning_codes": ["formula_suspect"]}


def test_bad_formula_does_not_block_other_usable_sources() -> None:
    damaged = hit(r"$$\int \sqrt{dx}=x+C$$")
    seen = {}

    def generator(model, query, context, **kwargs):
        seen["context"] = context
        return "Матрица — таблица [1]."

    result = generate_answer("local", "Вопрос?", [damaged, hit()], generator=generator)
    assert result.grounded and len(result.sources) == 1
    assert r"\sqrt{dx}" not in seen["context"]


def test_budget_never_sends_half_a_display_formula() -> None:
    context, sources = build_context([hit(r"$$\int " + "x+" * 1000 + r"dx=F(x)$$")], max_bytes=200)
    assert context == "" and sources == []


@pytest.mark.parametrize("code", ["``arr[99]``", "`arr[99]`", "``arr[99]`x``"])
def test_inline_code_numbers_are_never_citations(code) -> None:
    text = f"Код {code} имеет ссылку [1]."
    result = generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: text)
    assert result.answer == text


def test_multiline_code_inherits_adjacent_citation_and_is_not_renumbered() -> None:
    text = "Пример алгоритма из материала [1]:\n\n```python\n" + (
        "values = [99]  # a long code example requiring its surrounding explanation\n\n"
        "other = [98]   # another line in the same code block\n```"
    )
    result = generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: text)
    assert result.answer == text


def test_indented_code_numbers_do_not_become_source_ids() -> None:
    text = (
        "Пример из материала [1]:\n\n"
        "    values = [99]  # an indented code example with a long comment"
    )
    result = generate_answer("local", "Вопрос?", [hit()], generator=lambda *a, **k: text)
    assert result.answer == text


def test_citation_repair_runs_once_with_same_context_and_revalidates() -> None:
    seen = {}

    def first(model, question, context, *, language):
        seen['context'] = context
        return 'Определение без ссылки на переданный источник.'

    def repair(model, question, context, language, error):
        assert context == seen['context']
        assert error.reason == 'missing_citations'
        return 'Матрица — прямоугольная таблица элементов [1].'

    result = generate_answer('local', 'Вопрос?', [hit()], generator=first, citation_repair=repair)
    assert result.grounded and len(result.sources) == 1


def test_failed_citation_repair_does_not_bypass_validation() -> None:
    calls = []

    def repair(*args):
        calls.append(1)
        return 'Непроверенный факт [99].'

    with pytest.raises(CitationError) as failure:
        generate_answer(
            'local', 'Вопрос?', [hit()], generator=lambda *a, **k: 'Нет ссылки',
            citation_repair=repair,
        )
    assert calls == [1]
    assert failure.value.reason == 'unknown_source'


def test_suspect_source_never_triggers_citation_repair() -> None:
    with pytest.raises(CitationError, match='damaged'):
        generate_answer(
            'local', 'Вопрос?', [hit(r'$$\int \sqrt{dx}=x+C$$')],
            generator=lambda *a, **k: pytest.fail('must not generate'),
            citation_repair=lambda *a: pytest.fail('must not repair'),
        )


def test_repair_can_refuse_without_exposing_unreferenced_sources() -> None:
    result = generate_answer(
        'local', 'Вопрос?', [hit()], generator=lambda *a, **k: 'Нет ссылки',
        citation_repair=lambda *a: 'INSUFFICIENT_CONTEXT',
    )
    assert not result.grounded
    assert result.sources == []


def test_context_limits_five_sources_and_does_not_leak_sixth_to_generator() -> None:
    from dataclasses import replace

    hits = [replace(hit(f'Уникальный фрагмент номер {index}.'),
                    document_id=f'doc-{index}.md', chunk_id=f'chunk-{index}')
            for index in range(6)]
    seen = {}

    def generator(model, question, context, **kwargs):
        seen['context'] = context
        return 'Подтверждённое содержание [5].'

    result = generate_answer('local', 'Вопрос?', hits, generator=generator)
    assert 'doc-4.md' in seen['context']
    assert 'doc-5.md' not in seen['context']
    assert 'фрагмент номер 5.' not in seen['context']
    assert [source.document_id for source in result.sources] == ['doc-4.md']
    assert result.answer == 'Подтверждённое содержание [1].'


def test_citation_repair_does_not_accept_another_uncited_explanation() -> None:
    with pytest.raises(CitationError) as failure:
        generate_answer(
            'local', 'Вопрос?', [hit()], generator=lambda *a, **k: 'Нет ссылки',
            citation_repair=lambda *a: (
                'Определение [1].\n\n'
                'Ещё один содержательный абзац без указания подтверждающего источника.'
            ),
        )
    assert failure.value.reason == 'uncited_paragraph'
    assert failure.value.details['paragraph_index'] == 2
