"""Opt-in local embedding benchmark on a synthetic corpus; never downloads models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from study_agent.embeddings import EmbeddingIndexer, OllamaEmbedder, _request
from study_agent.indexer import DocumentIndexer, source_id
from study_agent.retrieval import retrieve
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--dimensions", type=int, required=True)
    parser.add_argument("--query-prefix", default="")
    parser.add_argument("--document-prefix", default="")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    corpus = json.loads(
        (Path(__file__).resolve().parents[1] / "tests/fixtures/rag_corpus.json").read_text()
    )
    embedder = OllamaEmbedder(
        options.model,
        options.dimensions,
        document_prefix=options.document_prefix,
        query_prefix=options.query_prefix,
    )
    with TemporaryDirectory() as temporary:
        root = Path(temporary) / "notes"
        root.mkdir()
        for name, text in corpus["documents"].items():
            (root / name).write_text(text, encoding="utf-8")
        storage = IndexStorage(Path(temporary) / "index.sqlite3")
        DocumentIndexer(storage).sync_source(LocalFolderSource(root))
        keys = [source_id(root)]
        started = perf_counter()
        first = EmbeddingIndexer(storage, embedder).sync_sources(keys)
        index_seconds = perf_counter() - started
        started = perf_counter()
        restarted = EmbeddingIndexer(IndexStorage(storage.path), embedder).sync_sources(keys)
        restart_seconds = perf_counter() - started
        modes = {}
        for mode in ("lexical", "semantic", "hybrid"):
            rows = []
            for case in corpus["queries"]:
                started = perf_counter()
                hits = retrieve(storage, keys, case["query"], mode=mode, embedder=embedder).hits
                names = [hit.document_id for hit in hits]
                rows.append(
                    {
                        **case,
                        "top3": names[:3],
                        "seconds": perf_counter() - started,
                        "reciprocal_rank": 1 / (names.index(case["expected"]) + 1)
                        if case["expected"] in names
                        else 0,
                    }
                )
            modes[mode] = {
                "recall_at_3": sum(row["expected"] in row["top3"] for row in rows) / len(rows),
                "mrr_at_8": sum(row["reciprocal_rank"] for row in rows) / len(rows),
                "mean_seconds": sum(row["seconds"] for row in rows) / len(rows),
                "queries": rows,
            }
        resident = [
            {key: item.get(key) for key in ("name", "size", "size_vram", "context_length")}
            for item in _request("/api/ps").get("models", [])
            if item.get("name") == options.model
        ]
        result = {
            "model": options.model,
            "digest": embedder.profile.model_digest,
            "dimensions": options.dimensions,
            "query_prefix": options.query_prefix,
            "document_prefix": options.document_prefix,
            "documents": len(corpus["documents"]),
            "chunks": first.embedded,
            "index_seconds": index_seconds,
            "restart_seconds": restart_seconds,
            "restart_skipped": restarted.skipped,
            "resident_model": resident,
            "modes": modes,
        }
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    mode: {key: value for key, value in report.items() if key != "queries"}
                    for mode, report in modes.items()
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
