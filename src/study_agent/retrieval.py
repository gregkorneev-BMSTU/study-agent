"""Exact local vector retrieval and reciprocal-rank fusion with SQLite FTS."""

from __future__ import annotations

import math
import sqlite3
import struct
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from study_agent.embeddings import Embedder, EmbeddingError, input_hash, validate_vector
from study_agent.math_content import (
    focus_excerpt,
    formula_warnings,
    is_math_query,
    math_relevance,
    math_signature_matches,
    supports_math_query,
)
from study_agent.search import SearchHit
from study_agent.storage import IndexStorage

SearchMode = Literal["lexical", "semantic", "hybrid"]


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[SearchHit]
    embedding_pending: bool = False


def hit_value(hit: SearchHit) -> dict[str, object]:
    return {**asdict(hit), "source_root": str(hit.source_root)}


def _hit(row: sqlite3.Row, score: int) -> SearchHit:
    return SearchHit(
        row["title"],
        row["relative_path"],
        row["text"],
        score,
        Path(row["root"]),
        row["page_number"],
        row["heading"],
        row["marker"],
        row["extraction_type"],
        row["chunk_id"],
    )


def _unique(hits: list[SearchHit], limit: int, query: str = "") -> list[SearchHit]:
    """Focus math and group candidates by source section, retaining provenance.

    A heading identifies its whole section even when split into adjacent chunks;
    without one, distinct pages or source markers remain independent results.
    """
    focused = [replace(hit, excerpt=focus_excerpt(hit.excerpt, query)) for hit in hits]
    if is_math_query(query):
        # Stable sorting retains retrieval order for equal lexical math intent.
        focused.sort(key=lambda hit: -math_relevance(hit.excerpt, query))
    grouped: dict[tuple[object, ...], SearchHit] = {}
    for hit in focused:
        location = (
            ("heading", hit.heading)
            if hit.heading
            else (
                ("page", hit.page_number) if hit.page_number is not None else ("marker", hit.marker)
            )
        )
        key = (hit.source_root, hit.document_id, *location)
        if key in grouped:
            representative = grouped[key]
            # Corrupt OCR in one sibling must not hide usable material from its section.
            if representative.quality_warnings and not formula_warnings(hit.excerpt):
                grouped[key] = replace(
                    hit, related_count=representative.related_count + 1, quality_warnings=[]
                )
            else:
                grouped[key] = replace(
                    representative, related_count=representative.related_count + 1
                )
        else:
            grouped[key] = replace(hit, quality_warnings=formula_warnings(hit.excerpt))
    selected = list(grouped.values())
    if is_math_query(query) and any(math_signature_matches(hit.excerpt, query) for hit in selected):
        selected = [hit for hit in selected if supports_math_query(hit.excerpt, query)]
    return selected[:limit]


def retrieve(
    storage: IndexStorage,
    source_ids: list[str],
    query: str,
    *,
    mode: SearchMode = "lexical",
    embedder: Embedder | None = None,
    limit: int = 8,
    min_similarity: float = 0.35,
    lexical_weight: float = 0.5,
) -> RetrievalResult:
    if mode not in ("lexical", "semantic", "hybrid"):
        raise ValueError("Unknown search mode")
    if not 0 <= min_similarity <= 1 or not 0 <= lexical_weight <= 1:
        raise ValueError("Invalid retrieval threshold or weight")
    if not query.strip() or not source_ids or limit < 1:
        return RetrievalResult([])
    candidate_limit = max(32, limit * 4)
    lexical = (
        []
        if mode == "semantic"
        else [
            _hit(row, max(1, round(float(row["rank"]) * 1_000_000)) if "rank" in row.keys() else 1)
            for row in storage.search(source_ids, query, candidate_limit)
        ]
    )
    if mode == "lexical":
        return RetrievalResult(_unique(lexical, limit, query))
    if embedder is None:
        raise EmbeddingError("Choose a local embedding model before semantic search")
    profile = embedder.profile
    rows = storage.retrieval_chunks(source_ids, profile)
    candidates = [
        row
        for row in rows
        if row["vector"] is not None
        and row["dimensions"] == profile.dimensions
        and row["input_hash"] == input_hash(profile.document_input(row["text"], row["heading"]))
    ]
    pending = len(candidates) < len(rows)
    semantic: list[SearchHit] = []
    if candidates:
        question = validate_vector(embedder.embed_query(query), profile.dimensions)
        for row in candidates:
            vector = struct.unpack(f"<{profile.dimensions}f", row["vector"])
            similarity = max(-1.0, min(1.0, math.sumprod(question, vector)))
            if similarity >= min_similarity:
                semantic.append(_hit(row, round(similarity * 1_000_000)))
        semantic.sort(key=lambda hit: (-hit.score, str(hit.source_root), hit.chunk_id))
        semantic = semantic[:candidate_limit]
    if mode == "semantic":
        return RetrievalResult(_unique(semantic, limit, query), pending)
    # RRF combines ranks instead of adding incompatible BM25 and cosine scales.
    scores: dict[str, float] = {}
    values: dict[str, SearchHit] = {}
    for group, weight in ((lexical, lexical_weight), (semantic, 1 - lexical_weight)):
        if weight == 0:
            continue
        for rank, hit in enumerate(group, 1):
            key = hit.chunk_id
            assert key is not None
            values[key] = hit
            scores[key] = scores.get(key, 0.0) + weight / (60 + rank)
    ranked = sorted(values, key=lambda key: (-scores[key], key))
    combined = [replace(values[key], score=round(scores[key] * 1_000_000)) for key in ranked]
    return RetrievalResult(_unique(combined, limit, query), pending)
