"""Qt uses the shared bridge for retrieval and server-selected answer context."""

from pathlib import Path

import pytest

from study_agent import ui


def test_qt_retrieval_keeps_profile_and_answer_context_on_backend(monkeypatch) -> None:
    calls = []
    profile = {"model": "local-embed", "dimensions": 3}

    def dispatch(request):
        calls.append(request)
        if request["command"] == "search":
            return {"ok": True, "result": {"hits": [{"excerpt": "untrusted UI text"}]}}
        if request["command"] == "answer":
            return {"ok": True, "result": {"answer": "From database [1]", "sources": []}}
        return {"ok": True, "result": {}}

    monkeypatch.setattr(ui, "dispatch", dispatch)
    result = ui._retrieve_request(
        {"roots": ["/notes"], "query": "matrix", "search_mode": "hybrid",
         "embedding": profile}, True, "local-llm",
    )
    assert [item["command"] for item in calls] == ["sync_source", "search", "answer"]
    assert calls[0]["embedding"] == profile
    assert calls[2]["embedding"] == profile
    assert calls[2]["roots"] == ["/notes"]
    assert "hits" not in calls[2]
    assert result["response"]["answer"] == "From database [1]"


def test_qt_search_without_llm_and_readable_error(monkeypatch) -> None:
    calls = []

    def dispatch(request):
        calls.append(request)
        return {"ok": True, "result": {"hits": []}}

    monkeypatch.setattr(ui, "dispatch", dispatch)
    ui._retrieve_request({"roots": [], "query": "matrix", "search_mode": "lexical"},
                         False, "")
    assert [item["command"] for item in calls] == ["search"]
    monkeypatch.setattr(ui, "dispatch", lambda _: {
        "ok": False, "error": {"message": "Локальная модель недоступна"},
    })
    with pytest.raises(RuntimeError, match="Локальная модель недоступна"):
        ui._backend({"command": "search"})


def test_answer_failure_preserves_search_results(monkeypatch) -> None:
    def dispatch(request):
        if request["command"] == "answer":
            return {"ok": False, "error": {"message": "No local LLM"}}
        return {"ok": True, "result": {"hits": [{"document_id": "notes.md"}]}}

    monkeypatch.setattr(ui, "dispatch", dispatch)
    result = ui._retrieve_request({"roots": [], "query": "matrix"}, True, "local-llm")
    assert result["hits"] == [{"document_id": "notes.md"}]
    assert result["answer_error"] == "No local LLM"


def test_bridge_hit_decodes_source_path() -> None:
    hit = ui._decode_hits([{
        "title": "Notes", "document_id": "notes.md", "excerpt": "text", "score": 1,
        "source_root": "/notes", "heading": "Matrix", "chunk_id": "chunk-1",
    }])[0]
    assert hit.source_root == Path("/notes")
    assert hit.heading == "Matrix"


def test_profile_change_discards_inflight_results() -> None:
    class Button:
        enabled = False

        def setEnabled(self, enabled):
            self.enabled = enabled

    class Window:
        _search_generation = 2
        ask_button = Button()
        find_button = Button()

        def _add_hit(self, *_args):
            pytest.fail("stale results must not render")

    window = Window()
    ui.MainWindow._retrieved_result(window, 1, {"hits": [{"invalid": "old result"}]})
    assert window.ask_button.enabled
    assert window.find_button.enabled


def test_lexical_sync_ignores_selected_unavailable_embedding(monkeypatch) -> None:
    calls = []

    def dispatch(request):
        calls.append(request)
        return {"ok": True, "result": {"hits": []}}

    monkeypatch.setattr(ui, "dispatch", dispatch)
    ui._retrieve_request({"roots": ["/notes"], "query": "matrix", "search_mode": "lexical",
                          "embedding": {"model": "deleted", "dimensions": 3}}, False, "")
    assert calls[0]["command"] == "sync_source"
    assert calls[0]["embedding"] is None


def test_explicit_preparation_uses_embedding_in_lexical_mode(monkeypatch) -> None:
    calls = []
    profile = {"model": "local-embed", "dimensions": 3}
    monkeypatch.setattr(ui, "set_status", lambda *_args: None)
    monkeypatch.setattr(ui, "_backend", lambda request: calls.append(request))

    class Window:
        sources = [Path("/notes")]
        search_state = object()
        embedding_state = object()
        search_mode_combo = type("Combo", (), {"currentData": lambda _: "lexical"})()
        _schedule_index = ui.MainWindow._schedule_index

        def _embedding_config(self):
            return profile

        def _queue_library(self, worker):
            worker.task()

    window = Window()
    window._schedule_index(Path("/notes"))
    ui.MainWindow.prepare_embeddings(window)
    assert calls[0]["embedding"] is None
    assert calls[1]["embedding"] == profile


@pytest.mark.parametrize("response, expected_document, expected_number", [
    (None, "found.md", None),
    ({"grounded": False, "sources": [], "answer": "Insufficient context"}, "found.md", None),
    ({"grounded": True, "sources": [{
        "title": "Cited", "document_id": "cited.md", "excerpt": "cited", "score": 1,
        "source_root": "/notes",
    }], "answer": "Evidence [1]"}, "cited.md", 1),
])
def test_result_displays_only_citation_numbered_grounded_sources(
    monkeypatch, response, expected_document, expected_number,
) -> None:
    monkeypatch.setattr(ui, "set_status", lambda *_args: None)

    class Button:
        def setEnabled(self, _enabled):
            pass

    class Window:
        _search_generation = 1
        search_state = object()
        ask_button = Button()
        find_button = Button()
        displayed = []

        def _add_hit(self, number, hit):
            self.displayed.append((number, hit.document_id))

        def _answer_loaded(self, *_args):
            pass

    result = {"hits": [{"title": "Found", "document_id": "found.md", "excerpt": "found",
                        "score": 1, "source_root": "/notes"}]}
    if response:
        result["response"] = response
    window = Window()
    ui.MainWindow._retrieved_result(window, 1, result)
    assert window.displayed == [(expected_number, expected_document)]
