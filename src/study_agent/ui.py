"""Cross-platform glass-inspired desktop interface for Study Agent."""

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
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
from study_agent.theme import build_stylesheet, tokens_for

DEFAULT_MODEL = "qwen3.5:4b"
SETTINGS = QSettings("StudyAgent", "StudyAgent")


def _brand_logo_path() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        bases = (Path(bundle_dir), Path(bundle_dir).parent / "Resources")
        candidates = tuple(base / "study_agent" / "assets" / "AppIcon_1024.png" for base in bases)
        return next((path for path in candidates if path.is_file()), candidates[0])
    return (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "StudyAgent_Apple_Icon_Kit"
        / "Master"
        / "AppIcon_1024.png"
    )


def named(widget: QWidget, name: str) -> QWidget:
    widget.setObjectName(name)
    return widget


def set_status(label: QLabel, text: str, state: str) -> None:
    """Update an existing status label's semantic visual state."""
    label.setText(text)
    label.setProperty("state", state)
    label.style().unpolish(label)
    label.style().polish(label)


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
    def __init__(self) -> None:
        super().__init__()
        self.background_color = QColor()

    def set_background_color(self, color: str) -> None:
        self.background_color = QColor(color)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background_color)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Study Agent")
        self.resize(1240, 820)
        self.setMinimumSize(760, 560)
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
        self._page_opacity = QGraphicsOpacityEffect(self.pages)
        self.pages.setGraphicsEffect(self._page_opacity)
        self._page_animation = QPropertyAnimation(self._page_opacity, b"opacity", self)
        self._page_animation.setDuration(150)
        self._page_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._system_hints = QGuiApplication.styleHints()
        self._system_hints.colorSchemeChanged.connect(self._system_theme_changed)
        self._apply_appearance()
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
        panel.setMinimumWidth(184)
        panel.setMaximumWidth(232)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(8)
        logo = QLabel()
        logo.setObjectName("brand-logo")
        logo.setFixedSize(32, 32)
        logo.setAccessibleName("Логотип Study Agent")
        ratio = 2.0
        icon_size = round(logo.width() * ratio)
        pixmap = QPixmap(str(_brand_logo_path())).scaled(
            icon_size,
            icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(ratio)
        logo.setPixmap(pixmap)
        brand_row.addWidget(logo)
        brand_row.addWidget(named(QLabel("Study Agent"), "brand"))
        brand_row.addStretch()
        layout.addLayout(brand_row)
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
        self.sidebar_status = named(QLabel("Ollama: проверка…"), "status")
        self.sidebar_status.setWordWrap(True)
        layout.addWidget(self.sidebar_status)
        return panel

    def _page(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        page = named(QFrame(), "content")
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
            "status",
        )
        self.search_state.setWordWrap(True)
        layout.addWidget(self.search_state)
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_content = QWidget()
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
        self.results_content.setAutoFillBackground(False)
        self.results_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.results_area.viewport().setAutoFillBackground(False)
        self.results_area.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
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
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(12)
        settings_scroll.setWidget(settings_content)
        settings_content.setAutoFillBackground(False)
        settings_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        settings_scroll.viewport().setAutoFillBackground(False)
        settings_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout.addWidget(settings_scroll, 1)
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
        self.model_state = named(QLabel("Список получаем с локального сервера Ollama."), "status")
        self.model_state.setWordWrap(True)
        card_layout.addWidget(self.model_state)
        settings_layout.addWidget(card)
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
        settings_layout.addWidget(privacy)
        appearance = named(QFrame(), "card")
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(20, 18, 20, 18)
        appearance_layout.setSpacing(10)
        appearance_layout.addWidget(named(QLabel("Внешний вид и доступность"), "eyebrow"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Как в системе", "system")
        self.theme_combo.addItem("Светлая", "light")
        self.theme_combo.addItem("Тёмная", "dark")
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(SETTINGS.value("appearance/theme", "system")))
        )
        self.theme_combo.setAccessibleName("Цветовая тема")
        self.theme_combo.setToolTip("Выберите тему приложения или следуйте системной теме.")
        self.theme_combo.currentIndexChanged.connect(self._appearance_changed)
        appearance_layout.addWidget(self.theme_combo)
        self.reduce_transparency = QCheckBox("Уменьшить прозрачность поверхностей")
        self.reduce_transparency.setChecked(
            SETTINGS.value("appearance/reduce_transparency", False, type=bool)
        )
        self.reduce_transparency.setToolTip(
            "Использовать непрозрачные поверхности с более чёткими границами."
        )
        self.reduce_transparency.toggled.connect(self._appearance_changed)
        appearance_layout.addWidget(self.reduce_transparency)
        self.high_contrast = QCheckBox("Повышенный контраст")
        self.high_contrast.setChecked(SETTINGS.value("appearance/high_contrast", False, type=bool))
        self.high_contrast.setToolTip("Усилить контраст текста, границ и клавиатурного фокуса.")
        self.high_contrast.toggled.connect(self._appearance_changed)
        appearance_layout.addWidget(self.high_contrast)
        self.reduce_motion = QCheckBox("Уменьшить движение")
        self.reduce_motion.setChecked(SETTINGS.value("appearance/reduce_motion", False, type=bool))
        self.reduce_motion.setToolTip("Отключить короткое затухание при переходе между разделами.")
        self.reduce_motion.toggled.connect(self._appearance_changed)
        appearance_layout.addWidget(self.reduce_motion)
        settings_layout.addWidget(appearance)
        settings_layout.addStretch()
        return page

    def _appearance_changed(self, _value: object = None) -> None:
        SETTINGS.setValue("appearance/theme", self.theme_combo.currentData())
        SETTINGS.setValue("appearance/reduce_transparency", self.reduce_transparency.isChecked())
        SETTINGS.setValue("appearance/high_contrast", self.high_contrast.isChecked())
        SETTINGS.setValue("appearance/reduce_motion", self.reduce_motion.isChecked())
        if self.reduce_motion.isChecked() and hasattr(self, "_page_animation"):
            self._page_animation.stop()
            self._page_opacity.setOpacity(1.0)
        self._apply_appearance()

    def _system_theme_changed(self, _scheme: object) -> None:
        if self.theme_combo.currentData() == "system":
            self._apply_appearance()

    def _resolved_theme(self) -> str:
        selected = self.theme_combo.currentData()
        if selected in ("light", "dark"):
            return str(selected)
        scheme = self._system_hints.colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        return "dark"

    def _apply_appearance(self) -> None:
        self.canvas.set_background_color(
            tokens_for(
                self._resolved_theme(),
                reduce_transparency=self.reduce_transparency.isChecked(),
                high_contrast=self.high_contrast.isChecked(),
            ).window
        )
        QApplication.instance().setStyleSheet(
            build_stylesheet(
                self._resolved_theme(),
                reduce_transparency=self.reduce_transparency.isChecked(),
                high_contrast=self.high_contrast.isChecked(),
            )
        )

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if not self.reduce_motion.isChecked():
            self._page_animation.stop()
            self._page_opacity.setOpacity(0.94)
            self._page_animation.setStartValue(0.94)
            self._page_animation.setEndValue(1.0)
            self._page_animation.start()

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
        set_status(self.sidebar_status, "Ollama: проверка…", "progress")
        set_status(self.model_state, "Список получаем с локального сервера Ollama.", "progress")
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
        if current in models:
            set_status(
                self.model_state,
                f"Установлено моделей: {len(models)}. Текущий выбор: {current}.",
                "success",
            )
        else:
            set_status(
                self.model_state,
                f"Модель «{current}» не найдена в Ollama. Установите её через Ollama "
                "или команду ollama pull.",
                "warning",
            )
        set_status(
            self.sidebar_status,
            "Ollama: подключена" if models else "Ollama запущена, моделей нет",
            "success" if models else "warning",
        )

    def _models_failed(self, message: str) -> None:
        set_status(self.sidebar_status, "Ollama: нет соединения", "error")
        set_status(self.model_state, message, "error")

    def save_model(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model:
            set_status(self.model_state, "Укажите имя установленной локальной модели.", "warning")
            return
        SETTINGS.setValue("model", model)
        set_status(self.model_state, f"Сохранена модель: {model}.", "success")

    def ask(self) -> None:
        query = self.question.text().strip()
        if not query:
            return
        if not self.sources:
            set_status(
                self.search_state,
                "Сначала добавьте папку с материалами в разделе «Библиотека».",
                "warning",
            )
            return
        self.question.clear()
        self.ask_button.setEnabled(False)
        set_status(self.search_state, "Ищу фрагменты в выбранных папках…", "progress")
        self._clear_results()
        worker = Worker(
            lambda: search_sources([LocalFolderSource(path) for path in self.sources], query)
        )
        worker.succeeded.connect(lambda hits: self._retrieved(query, hits))
        worker.failed.connect(self._search_failed)
        self._run(worker)

    def _retrieved(self, query: str, hits: list[SearchHit]) -> None:
        if not hits:
            set_status(
                self.search_state,
                "В выбранных материалах не нашёл фрагментов по этому запросу.",
                "warning",
            )
            self.ask_button.setEnabled(True)
            return
        set_status(
            self.search_state,
            f"Нашёл {len(hits)} релевантных фрагментов. Формирую ответ локально…",
            "progress",
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
        title_text = f"[{number}]  {hit.title}  ·  {hit.source_root.name}/{hit.document_id}"
        title = named(
            QPushButton(title_text), "link"
        )
        title.setToolTip(title_text)
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
        set_status(
            self.search_state,
            f"Ответ подготовлен локально по {min(len(hits), 5)} источникам.",
            "success",
        )
        self.ask_button.setEnabled(True)

    def _search_failed(self, message: str) -> None:
        set_status(self.search_state, message, "error")
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
