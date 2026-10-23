"""Simple local text retrieval for the first desktop workflow."""

import re
from dataclasses import dataclass
from pathlib import Path

from study_agent.sources import LocalFolderSource

TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


@dataclass(frozen=True)
class SearchHit:
    title: str
    document_id: str
    excerpt: str
    score: int
    source_root: Path


def search_sources(sources: list[LocalFolderSource], query: str, limit: int = 8) -> list[SearchHit]:
    """Rank selected text files by matching query terms and return short excerpts."""
    terms = {term.casefold() for term in TOKEN_RE.findall(query) if len(term) > 1}
    if not terms:
        return []

    hits: list[SearchHit] = []
    for source in sources:
        for document in source.list_documents():
            text = source.read(document.document_id)
            folded = text.casefold()
            score = sum(folded.count(term) for term in terms)
            if not score:
                continue
            best_term = max(terms, key=folded.count)
            position = folded.find(best_term)
            start = max(0, position - 180)
            end = min(len(text), position + 420)
            excerpt = text[start:end].strip()
            if start:
                excerpt = "…" + excerpt
            if end < len(text):
                excerpt += "…"
            hits.append(SearchHit(document.title, document.path, excerpt, score, source.root))

    return sorted(hits, key=lambda hit: (-hit.score, hit.document_id.casefold()))[:limit]
