"""The Qt fallback preserves the source's mathematics and never renders HTML."""

import pytest

from study_agent.math_display import has_math, readable_math


def test_nested_fraction_and_root_keep_structure() -> None:
    source = r"$$\int \sqrt{x}\,dx = \frac{2}{3}x^{\frac{3}{2}}+C$$"
    result = readable_math(source)
    assert "∫ √(x)" in result
    assert "(2)/(3)x^((3)/(2))+C" in result
    assert r"\," not in result


def test_fallback_preserves_unknown_or_malformed_notation() -> None:
    assert readable_math(r"$\unknown{x} + \frac{1}$") == r"\unknown{x} + \frac{1}"
    assert readable_math(r"$$\int \sqrt{dx} = x+C$$") == "∫ √(dx) = x+C"


def test_plain_text_html_and_code_are_not_interpreted() -> None:
    source = '<img src="https://example.com/image">\n```latex\n$\\int x$\n```'
    assert readable_math(source) == source


def test_math_detection_includes_ocr_but_not_normal_notes() -> None:
    assert has_math(r"\sqrt{x}")
    assert has_math(r"\(x^2\)")
    assert not has_math("Конспект по матрицам")


@pytest.mark.parametrize("source", [
    "Запишите `$x^2$` буквально.",
    r"Двойные ``$\sqrt{x}$ с ` внутри`` без преобразования.",
    "````latex\n$\\sqrt{x}$\n```\n$\\frac{1}{2}$\n````\n",
    "~~~latex\n$\\sqrt{x}$\n~~~\n",
    "```latex\n$\\sqrt{x}$\n",
    "    $\\sqrt{x}$\n    $x^2$\n",
    "\t$\\sqrt{x}$\n",
])
def test_code_is_literal_and_does_not_trigger_math_notice(source: str) -> None:
    assert readable_math(source) == source
    assert not has_math(source)


def test_math_outside_code_still_renders() -> None:
    source = r"`$\sqrt{x}$` и $\sqrt{x}$"
    assert readable_math(source) == r"`$\sqrt{x}$` и √(x)"
    assert has_math(source)
