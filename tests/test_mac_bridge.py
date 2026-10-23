from pathlib import Path

from study_agent import extractors, mac_bridge


def test_dispatch_lists_and_searches_selected_materials(tmp_path: Path) -> None:
    root = tmp_path / "Study Notes"
    root.mkdir()
    (root / "lecture.md").write_text("Графы и алгоритмы поиска", encoding="utf-8")
    (root / "ignore.docx").write_bytes(b"not supported yet")

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
    captured: dict[str, str] = {}

    def fake_answer(model: str, question: str, context: str) -> str:
        captured.update(model=model, question=question, context=context)
        return "Ответ [1]"

    monkeypatch.setattr(mac_bridge, "answer", fake_answer)
    response = mac_bridge.dispatch(
        {
            "command": "answer",
            "model": "qwen3.5:4b",
            "query": "Что изучается?",
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
    assert response["result"]["answer"] == "Ответ [1]"
    assert captured == {
        "model": "qwen3.5:4b",
        "question": "Что изучается?",
        "context": "[1] Study Notes/lecture.md\nМатериалы лекции",
    }


def test_dispatch_returns_structured_error_for_unknown_command() -> None:
    response = mac_bridge.dispatch({"request_id": "bad", "command": "unknown"})

    assert response["ok"] is False
    assert response["request_id"] == "bad"
    assert response["error"]["message"] == "Unknown backend command"


def test_dispatch_surfaces_missing_local_ocr_as_error(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "materials"
    root.mkdir()
    (root / "scan.png").write_bytes(b"synthetic image")

    def missing_ocr(path: Path) -> str:
        raise RuntimeError("Install local OCR support with: pip install '.[ocr]'.")

    monkeypatch.setattr(extractors, "_extract_image", missing_ocr)
    response = mac_bridge.dispatch(
        {"command": "search", "roots": [str(root)], "query": "lecture"}
    )

    assert response["ok"] is False
    assert "pip install '.[ocr]'" in response["error"]["message"]
