"""Cross-platform glass-inspired desktop interface for Study Agent."""

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from study_agent.ollama import answer, list_models
from study_agent.search import SearchHit, search_sources
from study_agent.sources import LocalFolderSource

DEFAULT_MODEL = "qwen3.5:4b"
SETTINGS = QSettings("StudyAgent", "StudyAgent")
STYLESHEET = """
* { color: #f4f5f8; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
QMainWindow { background: #10131a; }
QWidget#canvas { background: transparent; }
QFrame#glass, QFrame#card {
  background-color: rgba(255, 255, 255, 13);
  border: 1px solid rgba(255, 255, 255, 25);
  border-radius: 20px;
}
QFrame#sidebar {
  background-color: rgba(18, 23, 34, 218);
  border: 1px solid rgba(255,255,255,20);
  border-radius: 24px;
}
QLabel#brand { font-size: 19px; font-weight: 650; }
QLabel#title { font-size: 30px; font-weight: 650; }
QLabel#subtitle { color: rgba(236, 241, 250, 172); font-size: 14px; }
QLabel#muted { color: rgba(236, 241, 250, 155); }
QLabel#eyebrow { color: #9eabc4; font-size: 12px; font-weight: 650; }
QPushButton {
  background: rgba(255, 255, 255, 16); border: 1px solid rgba(255,255,255,26);
  border-radius: 13px; padding: 11px 15px; font-size: 14px;
}
QPushButton:hover { background: rgba(255,255,255,28); border-color: rgba(255,255,255,46); }
QPushButton:pressed { background: rgba(255,255,255,38); }
QPushButton#primary { background: #b8d5ff; color: #13223a; border: 0; font-weight: 650; }
QPushButton#primary:hover { background: #d0e2ff; }
QPushButton#nav {
  text-align: left; padding: 13px 16px; background: transparent;
  border: 0; color: #d9dfeb;
}
QPushButton#nav:checked {
  background: rgba(255,255,255,24); border: 1px solid rgba(255,255,255,25);
}
QPushButton#link {
  background: transparent; border: 0; color: #bed7ff;
  text-align: left; padding: 2px;
}
QLineEdit, QTextEdit, QComboBox {
  background: rgba(8, 11, 18, 132); border: 1px solid rgba(255,255,255,30);
  border-radius: 14px; padding: 12px 14px; selection-background-color: #607fae;
}
QTextEdit { padding: 14px; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView {
  background: #252b37; border: 1px solid #515a6b;
  selection-background-color: #465b7c;
}
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item {
  background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,18);
  border-radius: 14px; margin: 4px 0; padding: 12px;
}
QListWidget::item:selected { background: rgba(184,213,255,28); }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 4px; }
QScrollBar::handle:vertical {
  background: rgba(255,255,255,65); border-radius: 4px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def named(widget: QWidget, name: str) -> QWidget:
    widget.setObjectName(name)
    return widget


class Worker(QThread):
    """Run disk and local-model work without freezing the window."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self.task = task

    def run(self) -> None:
        try:
            self.succeeded.emit(self.task())
        except Exception as exc:  # surface expected OS and runtime errors in the window
            self.failed.emit(str(exc))


class Canvas(QWidget):
    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#10131a"))
        for x, y, radius, color in (
            (0.88, 0.06, 500, QColor(67, 102, 167, 72)),
            (0.06, 0.86, 460, QColor(91, 70, 130, 58)),
            (0.60, 1.04, 300, QColor(63, 125, 141, 34)),
        ):
            gradient = QRadialGradient(self.width() * x, self.height() * y, radius)
            color.setAlpha(90)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            painter.fillRect(self.rect(), gradient)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Study Agent")
        self.resize(1240, 820)
        self.setMinimumSize(900, 640)
        self.sources: list[Path] = self._saved_sources()
        self.workers: list[Worker] = []
        self.installed_models: list[str] = []
        self.current_page = 0
        self.canvas = named(Canvas(), "canvas")
        self.setCentralWidget(self.canvas)
        root = QHBoxLayout(self.canvas)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)
        root.addWidget(self._sidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._search_page())
        self.pages.addWidget(self._library_page())
        self.pages.addWidget(self._settings_page())
        root.addWidget(self.pages, 1)
        self.setStyleSheet(STYLESHEET)
        self._show_sources()
        self.refresh_models()

    @staticmethod
    def _saved_sources() -> list[Path]:
        values = SETTINGS.value("sources", [])
        if isinstance(values, str):
            values = [values]
        return [Path(value) for value in values if Path(value).is_dir()]

    def _save_sources(self) -> None:
        SETTINGS.setValue("sources", [str(path) for path in self.sources])

    def _sidebar(self) -> QFrame:
        panel = named(QFrame(), "sidebar")
        panel.setFixedWidth(232)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)
        brand = named(QLabel("◉  Study Agent"), "brand")
        layout.addWidget(brand)
        caption = named(QLabel("Локальная библиотека знаний"), "muted")
        caption.setWordWrap(True)
        layout.addWidget(caption)
        layout.addSpacing(22)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("⌕   Поиск", "▤   Библиотека", "⚙   Настройки")):
            button = named(QPushButton(label), "nav")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked=False, i=index: self._navigate(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addStretch()
        self.sidebar_status = named(QLabel("Ollama: проверка…"), "muted")
        self.sidebar_status.setWordWrap(True)
        layout.addWidget(self.sidebar_status)
        return panel

    def _page(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        page = named(QFrame(), "glass")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(17)
        layout.addWidget(named(QLabel(title), "title"))
        layout.addWidget(named(QLabel(subtitle), "subtitle"))
        return page, layout

    def _search_page(self) -> QWidget:
        page, layout = self._page(
            "Поиск по материалам", "Ответы формируются локальной моделью по выбранным источникам."
        )
        self.search_state = named(
            QLabel(
                "Добавьте папку с учебными материалами в разделе «Библиотека».",
            ),
            "muted",
        )
        self.search_state.setWordWrap(True)
        layout.addWidget(self.search_state)
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_area.setStyleSheet("background: transparent;")
        self.results_area.viewport().setStyleSheet("background: transparent;")
        self.results_content = QWidget()
        self.results_content.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_content)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        empty_card = named(QFrame(), "card")
        empty_layout = QVBoxLayout(empty_card)
        empty_layout.addWidget(
            named(QLabel("Здесь появятся найденные фрагменты и ответы."), "muted")
        )
        self.results_layout.addWidget(empty_card)
        self.results_layout.addStretch()
        self.results_area.setWidget(self.results_content)
        layout.addWidget(self.results_area, 1)
        prompt_row = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText("Спросите о лекциях, конспектах или учебниках…")
        self.question.returnPressed.connect(self.ask)
        prompt_row.addWidget(self.question, 1)
        self.ask_button = named(QPushButton("Спросить"), "primary")
        self.ask_button.clicked.connect(self.ask)
        prompt_row.addWidget(self.ask_button)
        layout.addLayout(prompt_row)
        return page

    def _library_page(self) -> QWidget:
        page, layout = self._page(
            "Библиотека", "Подключайте только те папки, которые хотите индексировать и искать."
        )
        actions = QHBoxLayout()
        add = named(QPushButton("＋  Добавить папку"), "primary")
        add.clicked.connect(self.add_source)
        actions.addWidget(add)
        actions.addStretch()
        layout.addLayout(actions)
        self.library_summary = named(QLabel("Поддерживаются файлы Markdown и TXT."), "muted")
        layout.addWidget(self.library_summary)
        self.source_list = QListWidget()
        layout.addWidget(self.source_list, 1)
        remove = QPushButton("Удалить выбранную папку из библиотеки")
        remove.clicked.connect(self.remove_source)
        layout.addWidget(remove, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _settings_page(self) -> QWidget:
        page, layout = self._page(
            "Настройки", "Модель запускается через Ollama на этом компьютере."
        )
        card = named(QFrame(), "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        card_layout.addWidget(named(QLabel("Локальная языковая модель"), "eyebrow"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setCurrentText(SETTINGS.value("model", DEFAULT_MODEL))
        self.model_combo.setPlaceholderText("Например, qwen3.5:4b")
        card_layout.addWidget(self.model_combo)
        model_actions = QHBoxLayout()
        refresh = QPushButton("Обновить список моделей")
        refresh.clicked.connect(self.refresh_models)
        model_actions.addWidget(refresh)
        save = named(QPushButton("Сохранить модель"), "primary")
        save.clicked.connect(self.save_model)
        model_actions.addWidget(save)
        model_actions.addStretch()
        card_layout.addLayout(model_actions)
        self.model_state = named(QLabel("Список получаем с локального сервера Ollama."), "muted")
        self.model_state.setWordWrap(True)
        card_layout.addWidget(self.model_state)
        layout.addWidget(card)
        privacy = named(QFrame(), "card")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(20, 18, 20, 18)
        privacy_layout.addWidget(named(QLabel("Конфиденциальность"), "eyebrow"))
        privacy_text = named(
            QLabel(
                "Запросы и найденные фрагменты отправляются только в локальный Ollama. "
                "Внешние модели не используются."
            ),
            "muted",
        )
        privacy_text.setWordWrap(True)
        privacy_layout.addWidget(privacy_text)
        layout.addWidget(privacy)
        layout.addStretch()
        return page

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _show_sources(self) -> None:
        if not hasattr(self, "source_list"):
            return
        self.source_list.clear()
        document_count = 0
        for path in self.sources:
            try:
                count = len(LocalFolderSource(path).list_documents())
            except (OSError, ValueError):
                count = 0
            document_count += count
            item = QListWidgetItem(f"{path.name or path}    ·    {count} документов\n{path}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.source_list.addItem(item)
        self.library_summary.setText(
            f"{len(self.sources)} папок · {document_count} файлов Markdown/TXT"
            if self.sources
            else "Поддерживаются файлы Markdown и TXT."
        )
        self.search_state.setText(
            f"Папок: {len(self.sources)} · файлов: {document_count}. Задайте вопрос по материалам."
            if document_count
            else "Добавьте папку с учебными материалами в разделе «Библиотека»."
        )

    def add_source(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Выберите папку с учебными материалами")
        if selected:
            path = Path(selected).resolve()
            if path not in self.sources:
                self.sources.append(path)
                self._save_sources()
                self._show_sources()

    def remove_source(self) -> None:
        item = self.source_list.currentItem()
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self.sources = [source for source in self.sources if source != path]
        self._save_sources()
        self._show_sources()

    def refresh_models(self) -> None:
        self.sidebar_status.setText("Ollama: проверка…")
        worker = Worker(list_models)
        worker.succeeded.connect(self._models_loaded)
        worker.failed.connect(self._models_failed)
        self._run(worker)

    def _models_loaded(self, models: list[str]) -> None:
        self.installed_models = models
        current = self.model_combo.currentText() or SETTINGS.value("model", DEFAULT_MODEL)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        self.model_combo.setCurrentText(current)
        self.model_state.setText(
            f"Установлено моделей: {len(models)}. Текущий выбор: {current}."
            if current in models
            else (
                f"Модель «{current}» не найдена в Ollama. Установите её через Ollama "
                "или команду ollama pull."
            )
        )
        self.sidebar_status.setText(
            "Ollama: подключена" if models else "Ollama запущена, моделей нет"
        )

    def _models_failed(self, message: str) -> None:
        self.sidebar_status.setText("Ollama: нет соединения")
        self.model_state.setText(message)

    def save_model(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model:
            self.model_state.setText("Укажите имя установленной локальной модели.")
            return
        SETTINGS.setValue("model", model)
        self.model_state.setText(f"Сохранена модель: {model}.")

    def ask(self) -> None:
        query = self.question.text().strip()
        if not query:
            return
        if not self.sources:
            self.search_state.setText(
                "Сначала добавьте папку с материалами в разделе «Библиотека»."
            )
            return
        self.question.clear()
        self.ask_button.setEnabled(False)
        self.search_state.setText("Ищу фрагменты в выбранных папках…")
        self._clear_results()
        worker = Worker(
            lambda: search_sources([LocalFolderSource(path) for path in self.sources], query)
        )
        worker.succeeded.connect(lambda hits: self._retrieved(query, hits))
        worker.failed.connect(self._search_failed)
        self._run(worker)

    def _retrieved(self, query: str, hits: list[SearchHit]) -> None:
        if not hits:
            self.search_state.setText(
                "В выбранных материалах не нашёл фрагментов по этому запросу."
            )
            self.ask_button.setEnabled(True)
            return
        self.search_state.setText(
            f"Нашёл {len(hits)} релевантных фрагментов. Формирую ответ локально…"
        )
        for number, hit in enumerate(hits, start=1):
            self._add_hit(number, hit)
        context = "\n\n".join(
            f"[{index}] {hit.source_root.name}/{hit.document_id}\n{hit.excerpt}"
            for index, hit in enumerate(hits[:5], start=1)
        )
        model = SETTINGS.value("model", DEFAULT_MODEL)
        worker = Worker(lambda: answer(str(model), query, context))
        worker.succeeded.connect(lambda response: self._answer_loaded(response, hits))
        worker.failed.connect(self._search_failed)
        self._run(worker)

    def _add_hit(self, number: int, hit: SearchHit) -> None:
        card = named(QFrame(), "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        title = named(
            QPushButton(f"[{number}]  {hit.title}  ·  {hit.source_root.name}/{hit.document_id}"),
            "link",
        )
        title.clicked.connect(lambda _checked=False, h=hit: self._open_document(h))
        layout.addWidget(title)
        excerpt = QLabel(hit.excerpt)
        excerpt.setWordWrap(True)
        excerpt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(excerpt)
        self.results_layout.addWidget(card)

    def _answer_loaded(self, response: str, hits: list[SearchHit]) -> None:
        card = named(QFrame(), "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(named(QLabel("Ответ модели"), "eyebrow"))
        answer_label = QLabel(response)
        answer_label.setWordWrap(True)
        answer_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(answer_label)
        self.results_layout.addWidget(card)
        self.search_state.setText(f"Ответ подготовлен локально по {min(len(hits), 5)} источникам.")
        self.ask_button.setEnabled(True)

    def _search_failed(self, message: str) -> None:
        self.search_state.setText(message)
        self.ask_button.setEnabled(True)

    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _open_document(self, hit: SearchHit) -> None:
        candidate = hit.source_root / hit.document_id
        if candidate.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate)))

    def _run(self, worker: Worker) -> None:
        self.workers.append(worker)
        worker.finished.connect(
            lambda: self.workers.remove(worker) if worker in self.workers else None
        )
        worker.start()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Study Agent")
    app.setOrganizationName("Study Agent")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
