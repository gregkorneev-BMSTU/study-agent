"""Local embedding protocol and cache lifecycle, without network/model weights."""

from pathlib import Path
from threading import Event

import pytest

from study_agent import embeddings
from study_agent.embeddings import (
    EmbeddingError,
    EmbeddingIndexer,
    EmbeddingProfile,
    OllamaEmbedder,
)
from study_agent.indexer import DocumentIndexer, source_id
from study_agent.sources import LocalFolderSource
from study_agent.storage import IndexStorage


class FakeEmbedder:
    def __init__(self, digest: str = "v1", **kwargs) -> None:
        self.profile = EmbeddingProfile("synthetic:latest", digest, 3, **kwargs)
        self.calls: list[list[str]] = []

    def embed_documents(self, inputs: list[str]) -> list[list[float]]:
        self.calls.append(inputs)
        return [[1.0, 2.0, 3.0] for _ in inputs]


def setup_index(tmp_path: Path):
    root = tmp_path / "materials"
    root.mkdir()
    (root / "notes.md").write_text("# Алгебра\nМатрица\n\n# Анализ\nПредел", encoding="utf-8")
    source = LocalFolderSource(root)
    storage = IndexStorage(tmp_path / "index.sqlite3")
    DocumentIndexer(storage).sync_source(source)
    return root, source, storage


def fake_ollama(monkeypatch, vectors=None, **metadata):
    calls = []

    def request(path, payload=None):
        calls.append((path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "synthetic:latest", "digest": "v1", **metadata}]}
        assert path == "/api/embed"
        return {"embeddings": vectors if vectors is not None else [[3, 4, 0]]}

    monkeypatch.setattr(embeddings, "_request", request)
    return calls


def test_ollama_batches_and_query_prefix_never_truncate(monkeypatch) -> None:
    calls = fake_ollama(monkeypatch)
    embedder = OllamaEmbedder("synthetic:latest", 3, query_prefix="query: ")
    assert embedder.embed_query("Что такое матрица?") == [0.6, 0.8, 0.0]
    request = next(payload for path, payload in calls if path == "/api/embed")
    assert request == {
        "model": "synthetic:latest",
        "input": ["query: Что такое матрица?"],
        "dimensions": 3,
        "truncate": False,
    }
    assert embedder.embed_documents([]) == []


@pytest.mark.parametrize(
    "vectors",
    [[], [[1, 2]], [[0, 0, 0]], [[True, 1, 2]], [[float("nan"), 1, 2]], [[float("inf"), 1, 2]]],
)
def test_reject_invalid_runtime_vectors(monkeypatch, vectors) -> None:
    fake_ollama(monkeypatch, vectors)
    embedder = OllamaEmbedder("synthetic:latest", 3)
    with pytest.raises(EmbeddingError):
        embedder.embed_documents(["text"])


@pytest.mark.parametrize(
    "metadata", [{"remote_host": "https://cloud.invalid"}, {"remote_model": "remote"}]
)
def test_cloud_model_is_rejected_before_sending_text(monkeypatch, metadata) -> None:
    calls = fake_ollama(monkeypatch, **metadata)
    with pytest.raises(EmbeddingError, match="Cloud"):
        OllamaEmbedder("synthetic:latest", 3)
    assert [path for path, _ in calls] == ["/api/tags"]


def test_missing_model_does_not_trigger_download(monkeypatch) -> None:
    calls = []

    def request(path, payload=None):
        calls.append(path)
        return {"models": []}

    monkeypatch.setattr(embeddings, "_request", request)
    with pytest.raises(EmbeddingError, match="not installed"):
        OllamaEmbedder("missing:latest", 3)
    assert calls == ["/api/tags"]


def test_model_replacement_is_detected_before_and_after_inference(monkeypatch) -> None:
    fake_ollama(monkeypatch)
    embedder = OllamaEmbedder("synthetic:latest", 3)
    state = {"digest": "v2"}
    calls = []

    def request(path, payload=None):
        calls.append(path)
        if path == "/api/tags":
            return {"models": [{"name": "synthetic:latest", "digest": state["digest"]}]}
        state["digest"] = "v2"
        return {"embeddings": [[1, 2, 3]]}

    monkeypatch.setattr(embeddings, "_request", request)
    with pytest.raises(EmbeddingError, match="changed"):
        embedder.embed_documents(["text"])
    assert "/api/embed" not in calls
    state["digest"] = "v1"
    with pytest.raises(EmbeddingError, match="changed"):
        embedder.embed_documents(["text"])
    assert "/api/embed" in calls


def test_cache_survives_restart_and_only_changed_input_is_embedded(tmp_path: Path) -> None:
    root, source, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()
    keys = [source_id(root)]
    first = EmbeddingIndexer(storage, embedder).sync_sources(keys, batch_size=1)
    assert first.embedded == 2 and len(embedder.calls) == 2
    assert embedder.calls[0] == ["Алгебра\n\n# Алгебра\nМатрица"]
    reopened = IndexStorage(storage.path)
    assert len(reopened.load_embeddings(keys, embedder.profile)) == 2
    assert EmbeddingIndexer(reopened, embedder).sync_sources(keys).skipped == 2
    assert len(embedder.calls) == 2

    (root / "notes.md").write_text("# Алгебра\nМатрица\n\n# Анализ\nНовый предел", encoding="utf-8")
    DocumentIndexer(reopened).sync_source(source)
    assert len(reopened.load_embeddings(keys, embedder.profile)) == 1
    report = EmbeddingIndexer(reopened, embedder).sync_sources(keys)
    assert report.embedded == 1 and report.skipped == 1
    assert len(embedder.calls) == 3
    assert "Новый предел" in embedder.calls[-1][0]

    source.root.joinpath("notes.md").unlink()
    DocumentIndexer(reopened).sync_source(source)
    assert reopened.load_embeddings(keys, embedder.profile) == []
    with reopened.connect() as db:
        assert db.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0] == 0


def test_profiles_are_independent_and_source_removal_cascades(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    keys = [source_id(root)]
    for embedder in (FakeEmbedder(), FakeEmbedder("v2"), FakeEmbedder(document_prefix="passage: ")):
        assert EmbeddingIndexer(storage, embedder).sync_sources(keys).embedded == 2
    with storage.connect() as db:
        assert db.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0] == 6
    assert storage.load_embeddings(["other"], embedder.profile) == []
    assert EmbeddingIndexer(storage, embedder).sync_sources([]).embedded == 0
    storage.remove_source(keys[0])
    assert storage.load_embeddings(keys, embedder.profile) == []
    with storage.connect() as db:
        assert db.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0] == 0


def test_changed_heading_invalidates_same_ordinal(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()
    keys = [source_id(root)]
    EmbeddingIndexer(storage, embedder).sync_sources(keys)
    with storage.connect() as db:
        db.execute("UPDATE chunks SET heading='Другая тема' WHERE ordinal=0")
    report = EmbeddingIndexer(storage, embedder).sync_sources(keys)
    assert report.embedded == 1 and report.skipped == 1


def test_inference_race_does_not_attach_old_vector_to_changed_chunk(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()

    def embed(inputs):
        with storage.connect() as db:
            db.execute("UPDATE chunks SET text='changed during inference' WHERE ordinal=0")
        return [[1, 2, 3] for _ in inputs]

    embedder.embed_documents = embed
    report = EmbeddingIndexer(storage, embedder).sync_sources([source_id(root)])
    assert report.embedded == 1 and report.stale == 1


def test_failure_and_cancel_preserve_saved_batches_and_resume(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()
    original = embedder.embed_documents

    def fail_second(inputs):
        if embedder.calls:
            raise EmbeddingError("runtime stopped")
        return original(inputs)

    embedder.embed_documents = fail_second
    with pytest.raises(EmbeddingError):
        EmbeddingIndexer(storage, embedder).sync_sources([source_id(root)], batch_size=1)
    assert len(storage.load_embeddings([source_id(root)], embedder.profile)) == 1
    embedder.embed_documents = original
    stop = Event()
    stop.set()
    assert (
        EmbeddingIndexer(storage, embedder)
        .sync_sources(
            [source_id(root)],
            cancel_token=stop,
        )
        .cancelled
    )
    report = EmbeddingIndexer(storage, embedder).sync_sources([source_id(root)])
    assert report.embedded == 1 and report.skipped == 1


def test_invalid_batch_is_not_partially_saved(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()
    embedder.embed_documents = lambda inputs: [[1, 2, 3], [float("nan"), 1, 2]]
    with pytest.raises(EmbeddingError):
        EmbeddingIndexer(storage, embedder).sync_sources([source_id(root)])
    assert storage.load_embeddings([source_id(root)], embedder.profile) == []


def test_transport_stays_on_loopback_without_proxy_or_redirect(monkeypatch) -> None:
    import json
    from urllib.request import ProxyHandler

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"embeddings": [[1, 2, 3]]}'

    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["data"] = json.loads(request.data)
            return Response()

    def build(*handlers):
        proxy, redirects = handlers
        assert isinstance(proxy, ProxyHandler) and proxy.proxies == {}
        with pytest.raises(EmbeddingError, match="redirect"):
            redirects.redirect_request(None, None, 302, "", {}, "https://external.invalid")
        return Opener()

    monkeypatch.setattr(embeddings, "build_opener", build)
    embeddings._request("/api/embed", {"input": ["synthetic"]})
    assert captured["url"] == "http://127.0.0.1:11434/api/embed"
    assert captured["data"] == {"input": ["synthetic"]}


def test_cancellation_during_inference_does_not_commit_batch(tmp_path: Path) -> None:
    root, _, storage = setup_index(tmp_path)
    embedder = FakeEmbedder()
    stop = Event()

    def embed(inputs):
        stop.set()
        return [[1, 2, 3] for _ in inputs]

    embedder.embed_documents = embed
    report = EmbeddingIndexer(storage, embedder).sync_sources(
        [source_id(root)],
        cancel_token=stop,
    )
    assert report.cancelled and report.embedded == 0
    assert storage.load_embeddings([source_id(root)], embedder.profile) == []
