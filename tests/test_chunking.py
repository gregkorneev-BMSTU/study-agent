"""Chunk boundaries must preserve structured extraction provenance."""

from study_agent.chunking import chunk_blocks
from study_agent.models import ExtractedBlock


def _block(text: str, **kwargs: object) -> ExtractedBlock:
    return ExtractedBlock(text, "pdf", "digital", **kwargs)


def test_chunks_do_not_cross_pages_and_keep_order() -> None:
    blocks = [_block("First page.", page_number=1), _block("Second page.", page_number=2)]

    chunks = chunk_blocks(blocks, max_chars=20, overlap=3)

    assert [chunk.text for chunk in chunks] == ["First page.", "Second page."]
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert [chunk.ordinal for chunk in chunks] == [0, 1]


def test_docx_metadata_and_empty_blocks() -> None:
    blocks = [
        ExtractedBlock("   ", "docx", "digital", heading="Ignored"),
        ExtractedBlock("A table cell", "docx", "digital", heading="Results", marker="table:1"),
    ]

    chunks = chunk_blocks(blocks)

    assert len(chunks) == 1
    assert chunks[0].page_number is None
    assert chunks[0].heading == "Results"
    assert chunks[0].marker == "table:1"


def test_long_text_splits_with_bounded_overlap() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta"

    chunks = chunk_blocks([_block(text)], max_chars=20, overlap=4)

    assert len(chunks) > 1
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(0 < len(chunk.text) <= 20 for chunk in chunks)


def test_invalid_chunk_parameters() -> None:
    import pytest

    with pytest.raises(ValueError):
        chunk_blocks([_block("text")], max_chars=10, overlap=10)
