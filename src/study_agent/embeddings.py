"""Explicit local-only Ollama embeddings and incremental indexing of saved chunks."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from threading import Event
from typing import TYPE_CHECKING, Protocol
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

if TYPE_CHECKING:
    from study_agent.storage import IndexStorage

INPUT_VERSION = 1
_LOCAL_URL = "http://127.0.0.1:11434"


class EmbeddingError(RuntimeError):
    """Embedding runtime is unavailable, incompatible or returned invalid data."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise EmbeddingError("Embedding endpoint must not redirect requests")


def _request(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    request = Request(
        _LOCAL_URL + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Ignore proxy settings: document text may only reach the local runtime.
    opener = build_opener(ProxyHandler({}), _NoRedirects())
    try:
        with opener.open(request, timeout=180 if payload is not None else 5) as response:
            result = json.loads(response.read())
    except (OSError, URLError, ValueError) as error:
        raise EmbeddingError("Local Ollama embedding request failed") from error
    if not isinstance(result, dict):
        raise EmbeddingError("Invalid Ollama response")
    return result


def _installed_digest(model: str) -> str:
    models = _request("/api/tags").get("models")
    if not isinstance(models, list):
        raise EmbeddingError("Invalid installed-model list")
    for item in models:
        if not isinstance(item, dict) or item.get("name") != model:
            continue
        if (
            item.get("remote_host")
            or item.get("remote_model")
            or model.endswith(("-cloud", ":cloud"))
        ):
            raise EmbeddingError("Cloud embedding models are not allowed")
        digest = item.get("digest")
        if isinstance(digest, str) and digest.strip():
            return digest
        raise EmbeddingError("Installed model has no digest")
    raise EmbeddingError("Embedding model is not installed; automatic download is disabled")


@dataclass(frozen=True)
class EmbeddingProfile:
    model: str
    model_digest: str
    dimensions: int
    document_prefix: str = ""
    query_prefix: str = ""

    def __post_init__(self) -> None:
        if (
            not self.model.strip()
            or not self.model_digest.strip()
            or isinstance(self.dimensions, bool)
            or not isinstance(self.dimensions, int)
            or self.dimensions < 1
        ):
            raise ValueError("model, model_digest and positive dimensions are required")

    @property
    def fingerprint(self) -> str:
        payload = {**asdict(self), "input_version": INPUT_VERSION}
        return input_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def document_input(self, text: str, heading: str | None) -> str:
        context = f"{heading}\n\n{text}" if heading else text
        return self.document_prefix + context


def input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_vector(vector: object, dimensions: int) -> list[float]:
    if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
        raise EmbeddingError("Embedding dimension mismatch")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
        raise EmbeddingError("Embedding contains non-numeric values")
    try:
        values = [float(value) for value in vector]
    except OverflowError as error:
        raise EmbeddingError("Embedding numeric value is too large") from error
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingError("Embedding must be finite and nonzero")
    return [value / norm for value in values]


class Embedder(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    def embed_documents(self, inputs: list[str]) -> list[list[float]]:
        """Embed already prepared inputs, without adding more prefixes."""
        ...


class OllamaEmbedder:
    def __init__(
        self,
        model: str,
        dimensions: int,
        *,
        document_prefix: str = "",
        query_prefix: str = "",
    ) -> None:
        self.profile = EmbeddingProfile(
            model,
            _installed_digest(model),
            dimensions,
            document_prefix,
            query_prefix,
        )

    def embed_documents(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in inputs):
            raise ValueError("Embedding inputs must be nonempty strings")
        self._check_model()
        result = _request(
            "/api/embed",
            {
                "model": self.profile.model,
                "input": inputs,
                "dimensions": self.profile.dimensions,
                "truncate": False,
            },
        )
        self._check_model()
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise EmbeddingError("Embedding batch size mismatch")
        return [validate_vector(vector, self.profile.dimensions) for vector in vectors]

    def embed_query(self, question: str) -> list[float]:
        if not question.strip():
            raise ValueError("Question must not be empty")
        return self.embed_documents([self.profile.query_prefix + question])[0]

    def _check_model(self) -> None:
        if _installed_digest(self.profile.model) != self.profile.model_digest:
            raise EmbeddingError("Embedding model changed; create a new profile and retry")


@dataclass
class EmbeddingReport:
    embedded: int = 0
    skipped: int = 0
    stale: int = 0
    cancelled: bool = False


class EmbeddingIndexer:
    """An explicit second indexing stage; never starts from ordinary text search."""

    def __init__(self, storage: IndexStorage, embedder: Embedder) -> None:
        self.storage = storage
        self.embedder = embedder

    def sync_sources(
        self,
        source_ids: list[str],
        *,
        batch_size: int = 32,
        cancel_token: Event | None = None,
    ) -> EmbeddingReport:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        report = EmbeddingReport()
        profile = self.embedder.profile
        # Snapshot rows before inference; writes recheck text/heading under a transaction.
        rows = self.storage.embedding_chunks(source_ids, profile.fingerprint)
        pending = []
        for row in rows:
            text = profile.document_input(row["text"], row["heading"])
            digest = input_hash(text)
            if row["input_hash"] == digest:
                report.skipped += 1
            else:
                pending.append((row["chunk_id"], text))
        for start in range(0, len(pending), batch_size):
            if cancel_token is not None and cancel_token.is_set():
                report.cancelled = True
                break
            batch = pending[start : start + batch_size]
            vectors = self.embedder.embed_documents([text for _, text in batch])
            if len(vectors) != len(batch):
                raise EmbeddingError("Embedding batch size mismatch")
            records = [
                (chunk_id, text, validate_vector(vector, profile.dimensions))
                for (chunk_id, text), vector in zip(batch, vectors, strict=True)
            ]
            if cancel_token is not None and cancel_token.is_set():
                report.cancelled = True
                break
            written = self.storage.put_embeddings(profile, records)
            report.embedded += written
            report.stale += len(records) - written
        return report
