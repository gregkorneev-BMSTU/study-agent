"""Exact local vector retrieval and reciprocal-rank fusion with SQLite FTS."""

from __future__ import annotations

import math
import re
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
    """Return one result per file while preserving every matched excerpt."""
    focused = [
        replace(
            hit,
            full_excerpt=hit.full_excerpt if hit.full_excerpt is not None else hit.excerpt,
            excerpt=focus_excerpt(hit.excerpt, query),
        )
        for hit in hits
    ]
    if is_math_query(query):
        # Stable sorting retains retrieval order for equal lexical math intent.
        focused.sort(key=lambda hit: -math_relevance(hit.excerpt, query))
    grouped: dict[tuple[object, ...], SearchHit] = {}
    for hit in focused:
        key = (hit.source_root, hit.document_id)
        if key in grouped:
            representative = grouped[key]
            excerpts = representative.matched_excerpts or [representative.excerpt]
            if hit.excerpt not in excerpts:
                excerpts.append(hit.excerpt)
            clean = not formula_warnings(hit.excerpt)
            base = hit if representative.quality_warnings and clean else representative
            previous_ids = representative.matched_chunk_ids or (
                [representative.chunk_id] if representative.chunk_id else []
            )
            grouped[key] = replace(
                base,
                related_count=len(excerpts) - 1,
                matched_excerpts=excerpts,
                matched_chunk_ids=list(dict.fromkeys(
                    [*previous_ids, *([hit.chunk_id] if hit.chunk_id else [])]
                )),
            )
        else:
            grouped[key] = replace(
                hit, quality_warnings=formula_warnings(hit.excerpt),
                matched_excerpts=[hit.excerpt],
                matched_chunk_ids=[hit.chunk_id] if hit.chunk_id else [],
            )
    selected = list(grouped.values())
    if is_math_query(query) and any(
        math_signature_matches(excerpt, query)
        for hit in selected for excerpt in (hit.matched_excerpts or [hit.excerpt])
    ):
        filtered = []
        for hit in selected:
            excerpts = [
                excerpt for excerpt in (hit.matched_excerpts or [hit.excerpt])
                if supports_math_query(excerpt, query)
            ]
            if excerpts:
                filtered.append(replace(
                    hit, excerpt=excerpts[0], matched_excerpts=excerpts,
                    related_count=len(excerpts) - 1,
                ))
        selected = filtered
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
        return RetrievalResult(_attach_neighbors(storage, _unique(lexical, limit, query)))
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
        selected = _unique(semantic, limit, query)
        return RetrievalResult(_attach_neighbors(storage, selected), pending)
    if candidates:
        # In hybrid mode lexical matches only refine candidates that pass the
        # semantic threshold; this prevents unrelated keyword hits from leaking in.
        semantic_ids = {hit.chunk_id for hit in semantic}
        exact_terms = set(re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE))
        lexical = [
            hit for hit in lexical
            if hit.chunk_id in semantic_ids
            or (exact_terms and exact_terms <= set(
                re.findall(r"[^\W_]+", hit.excerpt.casefold(), flags=re.UNICODE)
            ))
        ]
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
    selected = _unique(combined, limit, query)
    return RetrievalResult(_attach_neighbors(storage, selected), pending)


def _attach_neighbors(storage: IndexStorage, hits: list[SearchHit]) -> list[SearchHit]:
    all_ids = list(dict.fromkeys(
        chunk_id for hit in hits for chunk_id in
        (hit.matched_chunk_ids or ([hit.chunk_id] if hit.chunk_id else []))
    ))
    neighbors = storage.neighboring_chunks(all_ids)
    return [
        replace(
            hit,
            context_excerpts=list(dict.fromkeys(
                excerpt for chunk_id in (hit.matched_chunk_ids or [hit.chunk_id or ""])
                for excerpt in neighbors.get(chunk_id, [])
            )),
        )
        for hit in hits
    ]
