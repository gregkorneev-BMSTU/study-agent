"""JSON Lines bridge between the native macOS UI and the shared Python services."""

from __future__ import annotations

import json
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from study_agent.ollama import OllamaError, answer, list_models
from study_agent.search import search_sources
from study_agent.sources import LocalFolderSource


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """Run one native-app request and return a JSON-serializable response envelope."""
    request_id = request.get("request_id")
    try:
        command = request.get("command")
        if command == "list_sources":
            result = {"sources": [_source_summary(root) for root in _roots(request)]}
        elif command == "search":
            roots = _roots(request)
            query = _required_text(request, "query")
            hits = search_sources([LocalFolderSource(root) for root in roots], query)
            result = {
                "hits": [
                    {
                        "title": hit.title,
                        "document_id": hit.document_id,
                        "excerpt": hit.excerpt,
                        "score": hit.score,
                        "source_root": str(hit.source_root),
                    }
                    for hit in hits
                ]
            }
        elif command == "answer":
            context = "\n\n".join(
                f"[{index}] {hit['source_root'].rstrip('/').split('/')[-1]}/{hit['document_id']}\n"
                f"{hit['excerpt']}"
                for index, hit in enumerate(_hit_context(request), start=1)
            )
            language = request.get("language")
            result = {
                "answer": answer(
                    _required_text(request, "model"),
                    _required_text(request, "query"),
                    context,
                    language=language if language in ("en", "ru") else None,
                )
            }
        elif command == "list_models":
            result = {"models": list_models()}
        elif command == "diagnose_backend":
            result = _backend_diagnostics()
        else:
            raise ValueError("Unknown backend command")
        return {"request_id": request_id, "ok": True, "result": result}
    except (OSError, OllamaError, RuntimeError, TypeError, ValueError) as error:
        return {
            "request_id": request_id,
            "ok": False,
            "error": {"message": str(error)},
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
            find_spec("chandra") is not None and find_spec("PIL") is not None
        ),
        # Chandra manages its own model cache. Package presence cannot prove the weights exist.
        "ocr_weights_state": "unknown",
    }


def _required_text(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _hit_context(request: dict[str, Any]) -> list[dict[str, str]]:
    hits = request.get("hits")
    if not isinstance(hits, list):
        raise ValueError("hits must be a list")
    context = []
    for hit in hits[:5]:
        if not isinstance(hit, dict):
            raise ValueError("each hit must be an object")
        source_root = hit.get("source_root")
        document_id = hit.get("document_id")
        excerpt = hit.get("excerpt")
        if not all(isinstance(value, str) for value in (source_root, document_id, excerpt)):
            raise ValueError("each hit needs source_root, document_id and excerpt strings")
        context.append(
            {"source_root": source_root, "document_id": document_id, "excerpt": excerpt}
        )
    return context


def _source_summary(root: Path) -> dict[str, Any]:
    source = LocalFolderSource(root)
    return {
        "name": source.root.name,
        "path": str(source.root),
        "document_count": len(source.list_documents()),
    }


def main() -> int:
    """Read one JSON request per line and write one response per line."""
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            response = dispatch(request)
        except (json.JSONDecodeError, ValueError) as error:
            response = {"ok": False, "error": {"message": str(error)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
