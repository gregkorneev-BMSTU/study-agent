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


def _unique(hits: list[SearchHit], limit: int) -> list[SearchHit]:
    selected: list[SearchHit] = []
    for hit in hits:
        words = set(re.findall(r"\w+", hit.excerpt.casefold()))
        duplicate = False
        for other in selected:
            if (hit.source_root, hit.document_id) != (other.source_root, other.document_id):
                continue
            other_words = set(re.findall(r"\w+", other.excerpt.casefold()))
            if hit.excerpt == other.excerpt or (
                min(len(words), len(other_words)) >= 20
                and len(words & other_words) / min(len(words), len(other_words)) >= 0.85
            ):
                duplicate = True
                break
        if not duplicate:
            selected.append(hit)
        if len(selected) == limit:
            break
    return selected


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
        return RetrievalResult(_unique(lexical, limit))
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
        return RetrievalResult(_unique(semantic, limit), pending)
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
    return RetrievalResult(_unique(combined, limit), pending)
