"""Stable, provenance-preserving chunks from structured extraction blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from study_agent.models import ExtractedBlock

CHUNK_VERSION = 1


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_number: int | None
    heading: str | None
    marker: str | None
    extraction_type: str


def chunk_blocks(
    blocks: list[ExtractedBlock], *, max_chars: int = 1000, overlap: int = 120
) -> list[Chunk]:
    """Split each block independently so page/position metadata stays truthful."""
    if max_chars < 1 or overlap < 0 or overlap >= max_chars:
        raise ValueError("chunk size and overlap must satisfy 0 <= overlap < max_chars")
    chunks: list[Chunk] = []
    for block in blocks:
        content = block.text.strip()
        if not content:
            continue
        start = 0
        while start < len(content):
            end = min(start + max_chars, len(content))
            if end < len(content):
                section = content[start:end]
                boundaries = [match.end() for match in re.finditer(r"\n\n|[.!?]\s|\n|\s", section)]
                good = [point for point in boundaries if point >= max_chars // 2]
                if good:
                    end = start + max(good)
            part = content[start:end].strip()
            if part:
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
            if end == len(content):
                break
            start = max(start + 1, end - overlap)
    return chunks
