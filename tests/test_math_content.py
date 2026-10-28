"""Literal focusing and deliberately narrow OCR diagnostics on synthetic notes."""

import pytest

from study_agent.math_content import focus_excerpt, formula_warnings, math_relevance

TABLE = r"""## Интегралы

$$\int \sqrt{x^n} dx = F(x) + C$$

$$\int \frac{dx}{\sqrt{x}} = 2\sqrt{x}+C$$

$$\int \sin x dx = -\cos x+C$$

$$\int \sqrt{dx} = x+C$$

$$\int \sqrt{x} dx = \frac{2}{3}x^{3/2}+C$$
"""


@pytest.mark.parametrize(
    ("query", "target"),
    [
        ("интеграл корня из x", r"$$\int \sqrt{x} dx = \frac{2}{3}x^{3/2}+C$$"),
        ("интеграл 1/корень x", r"$$\int \frac{dx}{\sqrt{x}} = 2\sqrt{x}+C$$"),
        ("интеграл синуса x", r"$$\int \sin x dx = -\cos x+C$$"),
        (r"интеграл sqrt{x^n}", r"$$\int \sqrt{x^n} dx = F(x) + C$$"),
    ],
)
def test_focus_selects_literal_complete_target(query: str, target: str) -> None:
    assert focus_excerpt(TABLE, query) == target
    assert focus_excerpt(TABLE, query) in TABLE


def test_nonmath_query_preserves_full_source() -> None:
    assert focus_excerpt(TABLE, "таблица основных формул лекции") == TABLE


@pytest.mark.parametrize(
    "text",
    [
        r"$$\int \sqrt{dx} = x+C$$",
        r"$$\frac{x}{y$$",
        r"$$x = y",
        r"\[x = y",
        r"$$}x{$$",
    ],
)
def test_syntactic_suspicion(text: str) -> None:
    assert formula_warnings(text) == ["formula_suspect"]


def test_warning_does_not_claim_mathematical_validation() -> None:
    assert formula_warnings(r"$$1+1=3$$") == []
    assert formula_warnings("Обычный текст {пример}") == []
    assert formula_warnings(r"$$\int \sqrt{x} dx = F(x)$$") == []


def test_suspect_does_not_outrank_precise_formula() -> None:
    query = "интеграл корня из x"
    assert math_relevance(r"$$\int \sqrt{dx} = x$$", query) < math_relevance(
        r"$$\int \sqrt{x} dx = F(x)$$", query
    )


def test_focusing_never_builds_source_or_marker_from_text() -> None:
    text = "source: /private/other.md\n" + TABLE
    assert focus_excerpt(text, "интеграл корня из x") in TABLE


def test_unmatched_display_delimiter_cannot_be_paired_with_neighbor_formula() -> None:
    text = r"continuation x$$" + "\n\n" + r"$$\int \sqrt{x} dx=F(x)$$"
    assert focus_excerpt(text, "интеграл корня из x") == text
    assert formula_warnings(text) == ["formula_suspect"]


def test_cosine_and_sine_intents_differ() -> None:
    cosine = r"$$\int \cos x dx=\sin x+C$$"
    sine = r"$$\int \sin x dx=-\cos x+C$$"
    assert focus_excerpt(sine + "\n\n" + cosine, "интеграл косинуса x") == cosine


def test_general_integral_lecture_query_preserves_surrounding_text() -> None:
    assert focus_excerpt(TABLE, "таблица основных интегралов лекции") == TABLE


def test_narrow_sqrt_power_rule_ocr_heuristic() -> None:
    assert formula_warnings(r"$$\int \sqrt{x^n} dx = \frac{x^{n+1}}{n+1}+C$$") == [
        "formula_suspect"
    ]
    assert formula_warnings(r"$$\int \sqrt{x^n} dx = \frac{x^{n/2+1}}{n/2+1}+C$$") == []
    assert formula_warnings(r"$$\int x^n dx=\frac{x^{n+1}}{n+1}+C$$") == []


def test_sqrt_rule_heuristic_does_not_mix_neighboring_formulas() -> None:
    text = r"$$\int \sqrt{x^n}dx=F(x)$$" + "\n\n" + r"$$\int x^n dx=\frac{x^{n+1}}{n+1}+C$$"
    assert formula_warnings(text) == []


@pytest.mark.parametrize("wrapper", ["```latex\n{}\n```", "~~~latex\n{}\n~~~", "`{}`", "``{}``"])
def test_code_examples_are_not_promoted_to_standalone_facts(wrapper: str) -> None:
    from study_agent.math_content import math_signature_matches

    formula = r"$$\int \sin x dx = 123$$"
    text = (
        "Это неверный пример, не используйте:\n"
        + wrapper.format(formula)
        + "\nПравильный вариант в другом разделе."
    )
    assert focus_excerpt(text, "интеграл синуса x") == text
    assert math_relevance(text, "интеграл синуса x") == 0
    assert not math_signature_matches(text, "интеграл синуса x")


def test_formula_outside_code_retains_exact_source_offsets() -> None:
    formula = r"$$\int \sin x dx = -\cos x+C$$"
    text = "```latex\n" + r"$$\int \sin x dx = 123$$" + "\n```\n\n" + formula
    assert focus_excerpt(text, "интеграл синуса x") == formula


def test_inline_code_delimiters_do_not_unbalance_visible_formula() -> None:
    formula = r"$$\int \sqrt{x} dx=F(x)$$"
    text = "Синтаксис `$`, `\\[` и `$$`:\n\n" + formula
    assert focus_excerpt(text, "интеграл корня из x") == formula
    assert formula_warnings(text) == []


def test_adjacent_explicit_negation_is_not_discarded() -> None:
    text = "Это ошибочная формула, не используйте её:\n" + r"$$\int \sqrt{x} dx=123$$"
    assert focus_excerpt(text, "интеграл корня из x") == text


def test_adjacent_conditions_remain_literal_without_neighboring_formulas() -> None:
    formula = r"$$\int \sqrt{x} dx=F(x)+C$$"
    target = "Только для действительных x:\n" + formula + "\nпри x >= 0, где C — константа."
    text = (r"$$\int \sin x dx=G(x)$$" + "\n\n" + target
            + "\n\n" + r"$$\int \cos x dx=H(x)$$")
    assert focus_excerpt(text, "интеграл корня из x") == target
    assert target in text
