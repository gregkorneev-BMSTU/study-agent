from pathlib import Path
from types import SimpleNamespace

from study_agent import extractors, mac_bridge, storage


def _temporary_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "default_database_path", lambda: tmp_path / "index.sqlite3")


def _index(root: Path) -> None:
    response = mac_bridge.dispatch({"command": "index_source", "root": str(root)})
    assert response["ok"] is True


def test_dispatch_lists_and_searches_selected_materials(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "Study Notes"
    root.mkdir()
    (root / "lecture.md").write_text("Графы и алгоритмы поиска", encoding="utf-8")

    # Шаг исправления: заменяем .docx (который мы теперь поддерживаем)
    # на действительно игнорируемый формат (.xlsx)
    (root / "ignore.xlsx").write_bytes(b"not supported yet")

    listing = mac_bridge.dispatch(
        {"request_id": "list", "command": "list_sources", "roots": [str(root)]}
    )
    _index(root)
    search = mac_bridge.dispatch(
        {"request_id": "search", "command": "search", "roots": [str(root)], "query": "алгоритмы"}
    )

    assert listing["ok"] is True
    assert listing["result"]["sources"][0]["document_count"] == 1
    assert search["ok"] is True
    assert search["result"]["hits"][0]["document_id"] == "lecture.md"
    assert search["result"]["hits"][0]["source_root"] == str(root.resolve())


def test_dispatch_searches_saved_index_when_source_is_offline(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "offline notes"
    root.mkdir()
    (root / "lecture.md").write_text("Графы и алгоритмы поиска", encoding="utf-8")
    _index(root)
    root.rename(tmp_path / "disconnected notes")

    response = mac_bridge.dispatch(
        {"command": "search", "roots": [str(root)], "query": "алгоритмы"}
    )

    assert response["ok"] is True
    assert response["result"]["hits"][0]["document_id"] == "lecture.md"
    assert response["result"]["hits"][0]["source_root"] == str(root)


def test_dispatch_index_status_exposes_last_completed_sync(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "materials"
    root.mkdir()
    (root / "lecture.txt").write_text("Синхронный индекс", encoding="utf-8")
    _index(root)

    response = mac_bridge.dispatch({"command": "index_status", "root": str(root)})

    assert response["ok"] is True
    assert response["result"]["documents"] == 1
    assert response["result"]["last_indexed_at"]
    assert response["result"]["issues"] == []


def test_dispatch_index_status_restores_persisted_document_errors(
    tmp_path: Path, monkeypatch
) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "materials"
    root.mkdir()
    (root / "broken.txt").write_text("broken content", encoding="utf-8")
    index = storage.IndexStorage()
    from study_agent.indexer import INDEX_VERSION, document_id, source_id

    key = source_id(root)
    index.register_source(key, str(root))
    index.record_error(
        key,
        document_id(key, "broken.txt"),
        "broken.txt",
        "broken",
        ".txt",
        14,
        1,
        INDEX_VERSION,
        "document_extraction_failed",
    )

    response = mac_bridge.dispatch({"command": "index_status", "root": str(root)})

    assert response["ok"] is True
    assert response["result"]["failed"] == 1
    assert response["result"]["issues"] == [
        {
            "document_id": "broken.txt",
            "title": "broken",
            "code": "document_extraction_failed",
            "page_number": None,
        }
    ]


def test_dispatch_retrieves_answer_context_from_database(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "notes"
    root.mkdir()
    (root / "lecture.md").write_text(
        "Матрица — таблица элементов учебного материала.", encoding="utf-8"
    )
    _index(root)
    captured = {}

    def fake_answer(model, question, context, language=None):
        captured.update(model=model, question=question, context=context, language=language)
        return "Матрица — таблица элементов [1]."

    monkeypatch.setattr(mac_bridge, "answer", fake_answer)
    monkeypatch.setattr(mac_bridge, "ensure_local_model", lambda *_: "synthetic-v1")
    response = mac_bridge.dispatch(
        {
            "command": "answer",
            "roots": [str(root)],
            "model": "synthetic-llm",
            "query": "Матрица",
            "language": "en",
            "hits": [{"excerpt": "FORGED DOCUMENT", "source_root": "/secret"}],
        }
    )
    assert response["ok"] is True
    result = response["result"]
    assert result["grounded"] and result["sources"][0]["document_id"] == "lecture.md"
    assert "Матрица — таблица элементов" in captured["context"]
    assert "FORGED" not in captured["context"]
    assert captured["language"] == "en"


def test_dispatch_returns_structured_error_for_unknown_command() -> None:
    response = mac_bridge.dispatch({"request_id": "bad", "command": "unknown"})

    assert response["ok"] is False
    assert response["request_id"] == "bad"
    assert response["error"]["message"] == "Unknown backend command"


def test_dispatch_installs_ocr_model_only_when_requested(tmp_path: Path, monkeypatch) -> None:
    reported: list[dict[str, object]] = []

    def fake_download(progress_callback=None) -> Path:
        assert progress_callback is not None
        progress_callback({"current": 10, "total": 20})
        return tmp_path / "Chandra"

    monkeypatch.setattr(mac_bridge, "download_model", fake_download)
    response = mac_bridge.dispatch(
        {"request_id": "install", "command": "install_ocr_model"},
        progress_callback=reported.append,
    )

    assert response["ok"] is True
    assert response["result"]["ocr_weights_state"] == "installed"
    assert response["result"]["model_path"] == str(tmp_path / "Chandra")
    assert reported == [{"current": 10, "total": 20}]


def test_diagnostics_do_not_load_ocr_weights_or_contact_services(monkeypatch) -> None:
    installed = {"pypdfium2", "PIL", "chandra"}
    checked: list[str] = []

    def fake_find_spec(name: str) -> object | None:
        checked.append(name)
        return object() if name in installed else None

    monkeypatch.setattr(mac_bridge, "find_spec", fake_find_spec)
    monkeypatch.setattr(mac_bridge, "model_is_installed", lambda: False)
    response = mac_bridge.dispatch({"request_id": "diagnostics", "command": "diagnose_backend"})

    assert response == {
        "request_id": "diagnostics",
        "ok": True,
        "result": {
            "backend_healthy": True,
            "pdf_available": True,
            "ocr_runtime_available": False,
            "ocr_weights_state": "missing",
        },
    }
    assert checked == ["pypdfium2", "chandra", "PIL", "huggingface_hub"]


def test_dispatch_surfaces_missing_local_ocr_as_warning(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "materials"
    root.mkdir()
    (root / "scan.png").write_bytes(b"synthetic image")

    # Шаг исправления: мок теперь возвращает пустой список блоков с варнингом,
    # имитируя поведение нового контракта при ошибке
    def missing_ocr(path: Path):
        raise RuntimeError("Install local OCR support with: pip install '.[ocr]'.")

    monkeypatch.setattr(extractors, "_extract_image", missing_ocr)
    _index(root)
    response = mac_bridge.dispatch({"command": "search", "roots": [str(root)], "query": "lecture"})

    assert response["ok"] is True
    assert response["result"]["hits"] == []
    assert response["result"]["warnings"] == [
        {
            "document_id": "scan.png",
            "title": "scan",
            "code": "document_extraction_failed",
            "page_number": None,
        }
    ]


def test_search_returns_hits_and_safe_docx_warning(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    (tmp_path / "notes.txt").write_text("алгоритм поиска", encoding="utf-8")
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
    _index(tmp_path)
    result = mac_bridge.dispatch(
        {"command": "search", "roots": [str(tmp_path)], "query": "алгоритм"}
    )["result"]
    assert [hit["document_id"] for hit in result["hits"]] == ["notes.txt"]
    assert result["warnings"] == [
        {
            "document_id": "broken.docx",
            "title": "broken",
            "code": "document_extraction_failed",
            "page_number": None,
        }
    ]
    assert str(tmp_path) not in str(result["warnings"])


def test_search_warning_without_hits(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
    _index(tmp_path)
    result = mac_bridge.dispatch(
        {"command": "search", "roots": [str(tmp_path)], "query": "алгоритм"}
    )["result"]
    assert result["hits"] == []
    assert result["warnings"][0]["document_id"] == "broken.docx"


def test_failed_pdf_page_does_not_hide_later_page_or_other_document(
    tmp_path: Path, monkeypatch
) -> None:
    _temporary_index(tmp_path, monkeypatch)
    import sys

    (tmp_path / "scan.pdf").write_bytes(b"synthetic pdf")
    (tmp_path / "notes.txt").write_text("алгоритм заметки", encoding="utf-8")

    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def get_textpage(self):
            return SimpleNamespace(get_text_range=lambda: self.text, close=lambda: None)

        def render(self, scale: int):
            return SimpleNamespace(to_pil=lambda: object())

        def close(self) -> None:
            pass

    class PDF:
        def __init__(self, path: Path) -> None:
            pass

        def __iter__(self):
            return iter([Page(""), Page("алгоритм " * 8)])

        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=PDF))
    monkeypatch.setattr(
        extractors,
        "_ocr_image",
        lambda image: (_ for _ in ()).throw(RuntimeError("private path /tmp/secret")),
    )
    monkeypatch.setattr(extractors, "_cache_path", lambda path: tmp_path / "cache" / "pdf.json")
    _index(tmp_path)
    result = mac_bridge.dispatch(
        {"command": "search", "roots": [str(tmp_path)], "query": "алгоритм"}
    )["result"]
    assert {hit["document_id"] for hit in result["hits"]} == {"scan.pdf", "notes.txt"}
    assert result["warnings"] == [
        {
            "document_id": "scan.pdf",
            "title": "scan",
            "code": "ocr_failed",
            "page_number": 1,
        },
        {
            "document_id": "scan.pdf",
            "title": "scan",
            "code": "ocr_failed",
            "page_number": 2,
        },
    ]
    assert "/tmp/secret" not in str(result)


def test_search_reports_primary_indexing_until_source_is_ready(tmp_path: Path, monkeypatch) -> None:
    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "materials"
    root.mkdir()
    (root / "notes.txt").write_text("квантовая механика", encoding="utf-8")
    request = {"command": "search", "roots": [str(root)], "query": "квантовая"}
    assert mac_bridge.dispatch(request)["result"]["indexing"] is True
    observed: list[dict] = []

    def progress(event: dict) -> None:
        if event["phase"] == "scanning":
            observed.append(mac_bridge.dispatch(request)["result"])

    result = mac_bridge.dispatch(
        {"command": "index_source", "root": str(root)}, progress_callback=progress
    )
    assert result["ok"] is True
    assert observed[0]["indexing"] is True
    assert observed[0]["hits"] == []
    ready = mac_bridge.dispatch(request)["result"]
    assert ready["indexing"] is False
    assert ready["hits"][0]["document_id"] == "notes.txt"


def test_busy_index_request_can_be_retried_after_lock_release(tmp_path: Path, monkeypatch) -> None:
    from study_agent.indexer import _WriterLock
    from study_agent.storage import IndexStorage

    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "materials"
    root.mkdir()
    (root / "lesson.txt").write_text("retry token", encoding="utf-8")
    storage = IndexStorage(tmp_path / "index.sqlite3")
    request = {"command": "index_source", "root": str(root)}
    with _WriterLock(storage.path.with_suffix(".lock")):
        busy = mac_bridge.dispatch(request)
    assert busy["ok"] is False
    assert busy["error"]["code"] == "index_busy"
    assert mac_bridge.dispatch(request)["result"]["indexed"] == 1
    search = mac_bridge.dispatch({"command": "search", "roots": [str(root)], "query": "retry"})
    assert search["result"]["hits"]


def test_embedding_failure_keeps_text_index_searchable(tmp_path: Path, monkeypatch) -> None:
    from study_agent.embeddings import EmbeddingError

    _temporary_index(tmp_path, monkeypatch)
    root = tmp_path / "notes"
    root.mkdir()
    (root / "note.txt").write_text("Матрица содержит элементы по строкам.", encoding="utf-8")
    monkeypatch.setattr(
        mac_bridge, "_embedder", lambda _: (_ for _ in ()).throw(EmbeddingError("model removed"))
    )
    result = mac_bridge.dispatch(
        {
            "command": "sync_source",
            "root": str(root),
            "embedding": {"model": "removed", "dimensions": 3},
        }
    )
    assert not result["ok"] and result["error"]["code"] == "embedding_error"
    result = mac_bridge.dispatch({"command": "search", "roots": [str(root)], "query": "Матрица"})
    assert result["ok"] and result["result"]["hits"][0]["document_id"] == "note.txt"


def test_answer_failure_envelope_explains_cause_without_raw_text(
    tmp_path: Path, monkeypatch
) -> None:
    from study_agent.retrieval import RetrievalResult
    from study_agent.search import SearchHit

    raw_response = "PRIVATE GENERATED TEXT [19]"
    repair_feedback = []
    sample = SearchHit(
        "Synthetic",
        "note.txt",
        "A synthetic paragraph with enough context.",
        1,
        tmp_path,
        chunk_id="doc:0",
    )
    monkeypatch.setattr(mac_bridge, "_retrieve", lambda _: (None, [], RetrievalResult([sample])))
    monkeypatch.setattr(mac_bridge, "ensure_local_model", lambda *a: "synthetic")
    def answer(*args, **kwargs):
        if kwargs.get("citation_feedback"):
            repair_feedback.append(kwargs["citation_feedback"])
        return raw_response

    monkeypatch.setattr(mac_bridge, "answer", answer)
    result = mac_bridge.dispatch(
        {"command": "answer", "query": "Question?", "model": "synthetic-llm", "language": "ru"}
    )
    assert not result["ok"]
    error = result["error"]
    assert error["code"] == "invalid_citations" and error["reason"] == "unknown_source"
    assert error["details"] == {"source_count": 1, "invalid_sources": [19]}
    assert error["stage"] == "citation_repair" and error["model"] == "synthetic-llm"
    assert error["action"] and "Модель сослалась" in error["message"]
    assert raw_response not in str(error)
    assert repair_feedback == ["unknown_source; allowed source labels: [1]"]


def test_ollama_failure_during_citation_repair_is_identified(
    tmp_path: Path, monkeypatch
) -> None:
    from study_agent.ollama import OllamaError
    from study_agent.retrieval import RetrievalResult
    from study_agent.search import SearchHit

    sample = SearchHit(
        "Synthetic", "note.txt", "A synthetic paragraph with enough context.",
        1, tmp_path, chunk_id="doc:0",
    )
    monkeypatch.setattr(mac_bridge, "_retrieve", lambda _: (None, [], RetrievalResult([sample])))
    monkeypatch.setattr(mac_bridge, "ensure_local_model", lambda *a: "synthetic")
    calls = 0

    def answer(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "Unsupported citation [9]."
        raise OllamaError("Ollama returned an empty response.")

    monkeypatch.setattr(mac_bridge, "answer", answer)
    response = mac_bridge.dispatch({
        "command": "answer", "query": "Question?", "model": "synthetic-llm",
        "language": "en",
    })
    error = response["error"]
    assert error["code"] == "ollama_error"
    assert error["stage"] == "citation_repair"
    assert error["model"] == "synthetic-llm"
    assert error["reason"] == "Ollama returned an empty response."
