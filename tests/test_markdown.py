"""Markdown fixtures are synthetic and do not require OCR or a model."""

from study_agent.chunking import chunk_blocks
from study_agent.markdown import extract_markdown


def test_sections_keep_nested_heading_paths_and_source_lines() -> None:
    text = "Введение\n\n# Алгебра\nТекст\n\n## Матрицы ##\nОпределение\n\n# Анализ\nПредел\n"
    blocks = extract_markdown(text)
    assert [block.heading for block in blocks] == [
        None,
        "Алгебра",
        "Алгебра › Матрицы",
        "Анализ",
    ]
    assert [block.marker for block in blocks] == ["line:1", "line:3", "line:6", "line:9"]
    assert "".join(block.text for block in blocks) == text
    assert all(block.page_number is None for block in blocks)
    chunks = chunk_blocks(blocks)
    assert [chunk.heading for chunk in chunks] == [block.heading for block in blocks]


def test_fenced_and_indented_code_do_not_create_sections() -> None:
    text = "# Настоящий\n\n```md\n# Ложный\nЗаголовок\n===\n```\n\n    # Код\n\n## Второй\nтекст"
    blocks = extract_markdown(text)
    assert [block.heading for block in blocks] == ["Настоящий", "Настоящий › Второй"]
    assert "# Ложный" in blocks[0].text
    assert "    # Код" in blocks[0].text


def test_setext_and_longer_tilde_fences() -> None:
    text = "Курс\n====\n\n~~~~python\n## code\n~~~\n~~~~~\n\nРаздел\n------\nтекст"
    blocks = extract_markdown(text)
    assert [block.heading for block in blocks] == ["Курс", "Курс › Раздел"]
    assert "## code" in blocks[0].text
    assert "".join(block.text for block in blocks) == text


def test_fitting_code_and_table_stay_whole_when_prose_needs_splitting() -> None:
    code = "```python\nprint('hello')\nprint('world')\n```"
    table = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
    text = "# Раздел\n\n" + "слово " * 35 + "\n\n" + code + "\n\n" + table
    chunks = chunk_blocks(extract_markdown(text), max_chars=85, overlap=10)
    assert all(len(chunk.text) <= 85 for chunk in chunks)
    assert sum(code in chunk.text for chunk in chunks) == 1
    assert sum(table in chunk.text for chunk in chunks) == 1
    assert all(chunk.heading == "Раздел" for chunk in chunks)


def test_oversized_code_has_hard_size_limit_without_losing_lines() -> None:
    text = "```\n" + "line\n" * 80 + "```"
    chunks = chunk_blocks(extract_markdown(text), max_chars=40, overlap=0)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 40 for chunk in chunks)
    assert sum(chunk.text.count("line") for chunk in chunks) == 80


def test_optional_token_budget_uses_supplied_counter() -> None:
    chunks = chunk_blocks(
        extract_markdown("# Раздел\n\n" + "абвгд " * 40),
        max_chars=100,
        overlap=3,
        max_tokens=20,
        count_tokens=len,
    )
    assert all(len(chunk.text) <= 20 for chunk in chunks)


def test_token_limit_cannot_silently_ignore_missing_tokenizer() -> None:
    import pytest

    with pytest.raises(ValueError, match="token counter"):
        chunk_blocks(extract_markdown("text"), max_tokens=10)


def test_indented_code_keeps_leading_spaces_in_saved_chunk() -> None:
    chunks = chunk_blocks(extract_markdown("    print('code')\n    # still code\n"))
    assert len(chunks) == 1
    assert chunks[0].text == "    print('code')\n    # still code"
    assert chunks[0].heading is None
