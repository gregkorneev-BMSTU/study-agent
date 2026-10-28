"""Stable, provenance-preserving chunks from structured extraction blocks."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from study_agent.markdown import markdown_units
from study_agent.models import ExtractedBlock

CHUNK_VERSION = 2


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_number: int | None
    heading: str | None
    marker: str | None
    extraction_type: str


def chunk_blocks(
    blocks: list[ExtractedBlock],
    *,
    max_chars: int = 1000,
    overlap: int = 120,
    max_tokens: int | None = None,
    count_tokens: Callable[[str], int] | None = None,
) -> list[Chunk]:
    """Respect optional tokenizer limits; keep fitting Markdown units whole.

    Oversized code/tables must split to obey hard limits. Token counts refer to
    chunk text; embedding prefixes and heading context need their own allowance.
    """
    if max_chars < 1 or overlap < 0 or overlap >= max_chars:
        raise ValueError("chunk size and overlap must satisfy 0 <= overlap < max_chars")
    if max_tokens is not None and (max_tokens < 1 or count_tokens is None):
        raise ValueError("max_tokens requires a positive budget and a token counter")

    def fits(text: str) -> bool:
        return len(text) <= max_chars and (max_tokens is None or count_tokens(text) <= max_tokens)

    def clean(text: str, markdown: bool) -> str:
        return text.strip("\r\n") if markdown else text.strip()

    def split_text(content: str, *, markdown: bool = False) -> list[str]:
        result: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + max_chars, len(content))
            if not fits(content[start:end]):
                low, high = start, end
                while low < high:
                    middle = (low + high + 1) // 2
                    if fits(content[start:middle]):
                        low = middle
                    else:
                        high = middle - 1
                end = low
                if end == start:
                    raise ValueError("token budget cannot fit even one character")
            if end < len(content):
                section = content[start:end]
                boundaries = [match.end() for match in re.finditer(r"\n\n|[.!?]\s|\n|\s", section)]
                good = [point for point in boundaries if point >= len(section) // 2]
                if good:
                    candidate = start + max(good)
                    if fits(content[start:candidate]):
                        end = candidate
            part = clean(content[start:end], markdown)
            # Tokenization can change after stripping; check the actual payload.
            if part and not fits(part):
                raise ValueError("stripped chunk exceeds token budget")
            if part:
                result.append(part)
            if end == len(content):
                break
            start = max(start + 1, end - overlap)
        return result

    chunks: list[Chunk] = []
    for block in blocks:
        is_markdown = block.source_type == "markdown"
        content = clean(block.text, is_markdown)
        if not content.strip():
            continue
        if is_markdown:
            parts: list[str] = []
            pending = ""
            for unit in markdown_units(content):
                if fits(clean(pending + unit, True)):
                    pending += unit
                else:
                    if pending.strip():
                        parts.append(clean(pending, True))
                    pending = ""
                    if fits(clean(unit, True)):
                        pending = unit
                    else:
                        parts.extend(split_text(clean(unit, True), markdown=True))
            if pending.strip():
                parts.append(clean(pending, True))
        else:
            parts = split_text(content)
        for part in parts:
            chunks.append(
                Chunk(
                    len(chunks),
                    part,
                    block.page_number,
                    block.heading,
                    block.marker,
                    block.extraction_type,
                )
            )
    return chunks
