from pathlib import Path
from types import SimpleNamespace

from study_agent import storage, ui
from study_agent.indexer import source_id


def test_search_indexes_new_qt_source_before_query(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "default_database_path", lambda: tmp_path / "index.sqlite3")
    root = tmp_path / "notes"
    root.mkdir()
    (root / "lecture.txt").write_text("Алгоритмы поиска", encoding="utf-8")

    hits, warnings = ui._index_and_search([root], "алгоритмы")

    assert [hit.document_id for hit in hits] == ["lecture.txt"]
    assert warnings == []


def test_qt_add_indexes_and_remove_deletes_saved_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "default_database_path", lambda: tmp_path / "index.sqlite3")
    monkeypatch.setattr(ui, "set_status", lambda *_args: None)
    root = tmp_path / "notes"
    root.mkdir()
    (root / "lecture.txt").write_text("Алгоритмы поиска", encoding="utf-8")
    monkeypatch.setattr(ui.QFileDialog, "getExistingDirectory", lambda *_args: str(root))

    class WindowStub:
        sources: list[Path] = []
        search_state = object()
        source_list = SimpleNamespace(
            currentItem=lambda: SimpleNamespace(data=lambda _role: str(root))
        )
        queued: list[ui.Worker] = []
        _schedule_index = ui.MainWindow._schedule_index
        _removal_finished = ui.MainWindow._removal_finished

        def _save_sources(self) -> None:
            pass

        def _show_sources(self) -> None:
            pass

        def _queue_library(self, worker: ui.Worker) -> None:
            self.queued.append(worker)

    window = WindowStub()
    ui.MainWindow.add_source(window)
    assert window.sources == [root]
    assert len(window.queued) == 1
    window.queued.pop().task()
    assert storage.IndexStorage().search([source_id(root)], "алгоритмы")

    ui.MainWindow.remove_source(window)
    assert window.sources == [root]
    assert len(window.queued) == 1
    worker = window.queued.pop()
    worker.task()
    worker.succeeded.emit(None)
    assert window.sources == []
    assert not storage.IndexStorage().search([source_id(root)], "алгоритмы")


def test_qt_library_workers_run_in_order() -> None:
    class WindowStub:
        library_workers: list[ui.Worker] = []
        started: list[ui.Worker] = []
        _library_worker_finished = ui.MainWindow._library_worker_finished

        def _run(self, worker: ui.Worker) -> None:
            self.started.append(worker)

    window = WindowStub()
    first = ui.Worker(lambda: None)
    second = ui.Worker(lambda: None)
    ui.MainWindow._queue_library(window, first)
    ui.MainWindow._queue_library(window, second)
    assert window.started == [first]
    first.finished.emit()
    assert window.started == [first, second]


def test_qt_failed_remove_keeps_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ui, "set_status", lambda *_args: None)

    class WindowStub:
        sources: list[Path] = [tmp_path]
        search_state = object()
        source_list = SimpleNamespace(
            currentItem=lambda: SimpleNamespace(data=lambda _role: str(tmp_path))
        )
        queued: list[ui.Worker] = []

        def _save_sources(self) -> None:
            pass

        def _show_sources(self) -> None:
            pass

        def _queue_library(self, worker: ui.Worker) -> None:
            self.queued.append(worker)

    window = WindowStub()
    ui.MainWindow.remove_source(window)
    worker = window.queued.pop()
    worker.failed.emit("temporary failure")
    assert window.sources == [tmp_path]
