"""JSON Lines bridge between the native macOS UI and the shared Python services."""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import asdict
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from study_agent.embeddings import (
    EmbeddingError,
    EmbeddingIndexer,
    OllamaEmbedder,
    ensure_local_model,
    input_hash,
    list_embedding_models,
)
from study_agent.indexer import DocumentIndexer, IndexBusyError, source_id
from study_agent.ocr_model import download_model, model_is_installed
from study_agent.ollama import OllamaError, answer, list_models
from study_agent.rag import CitationError, generate_answer
from study_agent.retrieval import RetrievalResult, hit_value, retrieve
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


def dispatch(
    request: dict[str, Any],
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Run one native-app request and return a JSON-serializable response envelope."""
    request_id = request.get("request_id")
    try:
        command = request.get("command")
        if command == "list_sources":
            result = {"sources": [_source_summary(root) for root in _roots(request)]}
        elif command in ("index_source", "sync_source"):
            root = Path(_required_text(request, "root"))
            indexer = DocumentIndexer(IndexStorage())
            result = indexer.sync_source(
                LocalFolderSource(root),
                progress_callback=progress_callback,
                verify_hash=request.get("verify_hash") is True,
            ).to_dict()
            # Text remains searchable even when the optional embedding runtime fails.
            embedder = _embedder(request)
            if embedder is not None and not result["cancelled"]:
                report = EmbeddingIndexer(indexer.storage, embedder).sync_sources(
                    [source_id(root)],
                    progress_callback=progress_callback,
                )
                result["embeddings"] = asdict(report)
        elif command == "index_status":
            root = Path(_required_text(request, "root"))
            index = IndexStorage()
            result = DocumentIndexer(index).get_index_status(source_id(root))
            if request.get("embedding") is not None:
                try:
                    embedder = _embedder(request)
                    rows = index.embedding_chunks([source_id(root)], embedder.profile.fingerprint)

                    result["embedding_total"] = len(rows)
                    result["embedding_ready"] = sum(
                        row["input_hash"]
                        == input_hash(embedder.profile.document_input(row["text"], row["heading"]))
                        for row in rows
                    )
                except EmbeddingError:
                    result.update(
                        embedding_total=result["chunks"], embedding_ready=0, embedding_error=True
                    )
        elif command == "remove_index_source":
            root = Path(_required_text(request, "root"))
            DocumentIndexer(IndexStorage()).remove_source(source_id(root))
            result = {"removed": True}
        elif command == "search":
            index, keys, found = _retrieve(request)
            result = {
                "indexing": index.pending_sources(keys),
                "embedding_pending": found.embedding_pending,
                "search_mode": request.get("search_mode", "lexical"),
                "warnings": index.list_warnings(keys),
                "hits": [hit_value(hit) for hit in found.hits],
            }
        elif command == "answer":
            _, _, found = _retrieve(request)
            language = request.get("language")
            language = language if language in ("en", "ru") else None
            model = _required_text(request, "model")

            def local_answer(model: str, question: str, context: str, language: str | None) -> str:
                try:
                    ensure_local_model(model, "completion")
                except EmbeddingError as error:
                    raise ModelUnavailableError(str(error)) from error
                return answer(model, question, context, language=language)

            def repair_answer(
                model: str, question: str, context: str, language: str | None, error: CitationError
            ) -> str:
                return answer(
                    model, question, context, language=language,
                    citation_feedback=(
                        f"{error.reason}; supplied sources: {error.details['source_count']}"
                    ),
                )

            generated = generate_answer(
                model,
                _required_text(request, "query"),
                found.hits,
                language=language,
                generator=local_answer,
                citation_repair=repair_answer,
            )
            result = {
                "answer": generated.answer,
                "sources": [hit_value(hit) for hit in generated.sources],
                "grounded": generated.grounded,
            }
        elif command == "list_embedding_models":
            result = {"models": list_embedding_models()}
        elif command == "list_models":
            result = {"models": list_models()}
        elif command == "diagnose_backend":
            result = _backend_diagnostics()
        elif command == "install_ocr_model":
            result = {
                "ocr_weights_state": "installed",
                "model_path": str(download_model(progress_callback)),
            }
        else:
            raise ValueError("Unknown backend command")
        return {"request_id": request_id, "ok": True, "result": result}
    except (OSError, OllamaError, RuntimeError, TypeError, ValueError, sqlite3.Error) as error:
        diagnostic: dict[str, Any] = {}
        if isinstance(error, CitationError):
            language = request.get("language")
            diagnostic = {
                "reason": error.reason,
                "details": error.details,
                "action": error.action(language),
                "stage": "answer",
                "model": request.get("model"),
            }
        return {
            "request_id": request_id,
            "ok": False,
            "error": {
                "message": error.message(request.get("language"))
                if isinstance(error, CitationError)
                else str(error),
                **diagnostic,
                "code": (
                    "index_busy"
                    if isinstance(error, IndexBusyError)
                    else "embedding_required"
                    if isinstance(error, EmbeddingRequiredError)
                    else "embedding_error"
                    if isinstance(error, EmbeddingError)
                    else "model_unavailable"
                    if isinstance(error, ModelUnavailableError)
                    else "invalid_citations"
                    if isinstance(error, CitationError)
                    else "backend_error"
                ),
            },
        }


def _roots(request: dict[str, Any]) -> list[Path]:
    roots = request.get("roots")
    if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
        raise ValueError("roots must be a list of folder paths")
    return [Path(root) for root in roots]


def _backend_diagnostics() -> dict[str, Any]:
    """Report bundled dependency presence without importing models or contacting services."""
    return {
        "backend_healthy": True,
        "pdf_available": find_spec("pypdfium2") is not None,
        "ocr_runtime_available": (
            find_spec("chandra") is not None
            and find_spec("PIL") is not None
            and find_spec("huggingface_hub") is not None
        ),
        "ocr_weights_state": "installed" if model_is_installed() else "missing",
    }


def _required_text(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


class EmbeddingRequiredError(RuntimeError):
    pass


class ModelUnavailableError(RuntimeError):
    pass


def _embedder(request: dict[str, Any]) -> OllamaEmbedder | None:
    config = request.get("embedding")
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("embedding must be an object")
    model = _required_text(config, "model")
    dimensions = config.get("dimensions")
    if (
        isinstance(dimensions, bool)
        or not isinstance(dimensions, int)
        or not 1 <= dimensions <= 16384
    ):
        raise ValueError("embedding dimensions must be between 1 and 16384")
    document_prefix = config.get("document_prefix", "")
    query_prefix = config.get("query_prefix", "")
    if not all(
        isinstance(value, str) and len(value) <= 1024 for value in (document_prefix, query_prefix)
    ):
        raise ValueError("embedding prefixes must be strings of at most 1024 characters")
    return OllamaEmbedder(
        model, dimensions, document_prefix=document_prefix, query_prefix=query_prefix
    )


def _retrieve(request: dict[str, Any]) -> tuple[IndexStorage, list[str], RetrievalResult]:
    roots = _roots(request)
    query = _required_text(request, "query")
    mode = request.get("search_mode", "lexical")
    if mode not in ("lexical", "semantic", "hybrid"):
        raise ValueError("Unknown search mode")
    embedder = _embedder(request) if mode != "lexical" else None
    if mode != "lexical" and embedder is None:
        raise EmbeddingRequiredError("Choose an installed embedding model in Settings")
    index = IndexStorage()
    keys = [source_id(root) for root in roots]
    found = retrieve(index, keys, query, mode=mode, embedder=embedder)
    return index, keys, found


def _source_summary(root: Path) -> dict[str, Any]:
    try:
        source = LocalFolderSource(root)
        return {
            "name": source.root.name,
            "path": str(source.root),
            "document_count": len(source.list_documents()),
            "available": True,
        }
    except OSError:
        index = IndexStorage()
        status = DocumentIndexer(index).get_index_status(source_id(root))
        return {
            "name": root.name,
            "path": str(root),
            "document_count": status["documents"],
            "available": False,
        }


def main() -> int:
    """Read one JSON request per line and write one response per line."""
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")

            request_id = request.get("request_id")

            def report_progress(event: dict[str, Any], request_id: Any = request_id) -> None:
                sys.stdout.write(
                    json.dumps(
                        {
                            "event": "progress",
                            "request_id": request_id,
                            "result": event,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                sys.stdout.flush()

            response = dispatch(request, progress_callback=report_progress)
        except (json.JSONDecodeError, ValueError) as error:
            response = {"ok": False, "error": {"message": str(error)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
