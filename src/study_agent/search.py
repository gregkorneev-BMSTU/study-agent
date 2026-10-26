"""Lexical retrieval from the persistent document index."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from study_agent.indexer import source_id
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


@dataclass(frozen=True)
class SearchHit:
    title: str
    document_id: str
    excerpt: str
    score: int
    source_root: Path
    page_number: int | None = None
    heading: str | None = None
    marker: str | None = None
    extraction_type: str | None = None
    chunk_id: str | None = None
    related_count: int = 0
    quality_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchWarning:
    document_id: str
    title: str
    code: str
    page_number: int | None = None


def search_sources(
    sources: list[LocalFolderSource],
    query: str,
    limit: int = 8,
    *,
    warnings: list[SearchWarning] | None = None,
    storage: IndexStorage | None = None,
) -> list[SearchHit]:
    """Search saved chunks without opening or extracting source documents."""
    index = storage or IndexStorage()
    keys = [source_id(source.root) for source in sources]
    if warnings is not None:
        warnings.extend(SearchWarning(**item) for item in index.list_warnings(keys))
    rows = index.search(keys, query, limit)
    return [
        SearchHit(
            title=row["title"],
            document_id=row["relative_path"],
            excerpt=row["text"],
            score=max(1, round(float(row["rank"]) * 1_000_000)) if "rank" in row.keys() else 1,
            source_root=Path(row["root"]),
            page_number=row["page_number"],
            heading=row["heading"],
            marker=row["marker"],
            extraction_type=row["extraction_type"],
            chunk_id=row["chunk_id"],
        )
        for row in rows
    ]
