from pathlib import Path
from types import SimpleNamespace

from study_agent import extractors, mac_bridge


def test_dispatch_lists_and_searches_selected_materials(tmp_path: Path) -> None:
    root = tmp_path / "Study Notes"
    root.mkdir()
    (root / "lecture.md").write_text("Графы и алгоритмы поиска", encoding="utf-8")

    # Шаг исправления: заменяем .docx (который мы теперь поддерживаем)
    # на действительно игнорируемый формат (.xlsx)
    (root / "ignore.xlsx").write_bytes(b"not supported yet")

    listing = mac_bridge.dispatch(
        {"request_id": "list", "command": "list_sources", "roots": [str(root)]}
    )
    search = mac_bridge.dispatch(
        {"request_id": "search", "command": "search", "roots": [str(root)], "query": "алгоритмы"}
    )

    assert listing["ok"] is True
    assert listing["result"]["sources"][0]["document_count"] == 1
    assert search["ok"] is True
    assert search["result"]["hits"][0]["document_id"] == "lecture.md"
    assert search["result"]["hits"][0]["source_root"] == str(root.resolve())


def test_dispatch_uses_same_local_answer_context(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_answer(
        model: str,
        question: str,
        context: str,
        language: str | None = None,
    ) -> str:
        captured.update(model=model, question=question, context=context, language=language)
        return "Ответ"

    monkeypatch.setattr(mac_bridge, "answer", fake_answer)
    response = mac_bridge.dispatch(
        {
            "command": "answer",
            "model": "qwen3.5:4b",
            "query": "Что изучается?",
            "language": "en",
            "hits": [
                {
                    "source_root": "/tmp/Study Notes",
                    "document_id": "lecture.md",
                    "excerpt": "Материалы лекции",
                }
            ],
        }
    )

    assert response["ok"] is True
    assert response["result"]["answer"] == "Ответ"
    assert captured == {
        "model": "qwen3.5:4b",
        "question": "Что изучается?",
        "context": "[1] Study Notes/lecture.md\nМатериалы лекции",
        "language": "en",
    }


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
    root = tmp_path / "materials"
    root.mkdir()
    (root / "scan.png").write_bytes(b"synthetic image")

    # Шаг исправления: мок теперь возвращает пустой список блоков с варнингом,
    # имитируя поведение нового контракта при ошибке
    def missing_ocr(path: Path):
        raise RuntimeError("Install local OCR support with: pip install '.[ocr]'.")

    monkeypatch.setattr(extractors, "_extract_image", missing_ocr)
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


def test_search_returns_hits_and_safe_docx_warning(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("алгоритм поиска", encoding="utf-8")
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
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


def test_search_warning_without_hits(tmp_path: Path) -> None:
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
    result = mac_bridge.dispatch(
        {"command": "search", "roots": [str(tmp_path)], "query": "алгоритм"}
    )["result"]
    assert result["hits"] == []
    assert result["warnings"][0]["document_id"] == "broken.docx"


def test_failed_pdf_page_does_not_hide_later_page_or_other_document(
    tmp_path: Path, monkeypatch
) -> None:
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
        }
    ]
    assert "/tmp/secret" not in str(result)
