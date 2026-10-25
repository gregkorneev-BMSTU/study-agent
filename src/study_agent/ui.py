"""Cross-platform glass-inspired desktop interface for Study Agent."""

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSettings,
    QSize,
    Qt,
    QThread,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
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
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from study_agent.ollama import answer, list_models
from study_agent.search import SearchHit, SearchWarning, search_sources
from study_agent.sources import LocalFolderSource
from study_agent.switch import AppleSwitch
from study_agent.theme import ThemeTokens, build_stylesheet, tokens_for

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


def _tinted_symbol_icon(name: str, color: str) -> QIcon:
    path = _sf_symbol_path(name)
    source = QPixmap(str(path))
    source.setDevicePixelRatio(3)
    tinted = QPixmap(source.size())
    tinted.setDevicePixelRatio(3)
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(0, 0, 24, 24, QColor(color))
    painter.end()
    return QIcon(tinted)


def _sf_symbol_path(name: str) -> Path:
    return Path(__file__).parent / "assets" / "sf_symbols" / f"{name}.png"


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
        self._build_menu_bar()
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

    def _build_menu_bar(self) -> None:
        menu_bar: QMenuBar = self.menuBar()
        menu_bar.setNativeMenuBar(True)
        self._menus: list[QMenu] = []

        def add_menu(label: str) -> QMenu:
            menu = menu_bar.addMenu(label)
            self._menus.append(menu)
            return menu

        app_menu = add_menu("Study Agent")
        about = QAction("Об Study Agent", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "Study Agent",
                "Локальный поиск и анализ учебных материалов.\n\n"
                "Файлы остаются на этом компьютере; ответы формируются через Ollama.",
            )
        )
        app_menu.addAction(about)
        preferences = QAction("Настройки…", self)
        preferences.setMenuRole(QAction.MenuRole.PreferencesRole)
        preferences.triggered.connect(lambda: self._navigate(2))
        app_menu.addAction(preferences)
        app_menu.addSeparator()
        quit_action = QAction("Завершить Study Agent", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(QApplication.quit)
        app_menu.addAction(quit_action)

        file_menu = add_menu("Файл")
        add_source = QAction("Добавить папку…", self)
        add_source.setShortcut(QKeySequence.StandardKey.Open)
        add_source.triggered.connect(self.add_source)
        file_menu.addAction(add_source)
        remove_source = QAction("Удалить выбранную папку", self)
        remove_source.triggered.connect(self.remove_source)
        file_menu.addAction(remove_source)
        file_menu.addSeparator()
        refresh_models = QAction("Обновить список моделей Ollama", self)
        refresh_models.triggered.connect(self.refresh_models)
        file_menu.addAction(refresh_models)

        edit_menu = add_menu("Правка")
        self.edit_actions: dict[str, QAction] = {}
        edit_commands = (
            ("undo", "Отменить", QKeySequence.StandardKey.Undo),
            ("redo", "Повторить", QKeySequence.StandardKey.Redo),
            ("cut", "Вырезать", QKeySequence.StandardKey.Cut),
            ("copy", "Копировать", QKeySequence.StandardKey.Copy),
            ("paste", "Вставить", QKeySequence.StandardKey.Paste),
            ("select_all", "Выделить всё", QKeySequence.StandardKey.SelectAll),
        )
        for command, label, shortcut in edit_commands:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda _checked=False, name=command: self._edit_command(name))
            edit_menu.addAction(action)
            self.edit_actions[command] = action
        edit_menu.aboutToShow.connect(self._update_edit_actions)
        QApplication.instance().focusChanged.connect(lambda _old, _new: self._update_edit_actions())
        for line_edit in self.findChildren(QLineEdit):
            line_edit.selectionChanged.connect(self._update_edit_actions)
            line_edit.textChanged.connect(self._update_edit_actions)
        QApplication.clipboard().dataChanged.connect(self._update_edit_actions)

        view_menu = add_menu("Вид")
        self.view_actions: dict[int, QAction] = {}
        for index, label in enumerate(("Поиск", "Библиотека", "Настройки")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(index == 0)
            action.triggered.connect(lambda _checked=False, page=index: self._navigate(page))
            view_menu.addAction(action)
            self.view_actions[index] = action
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Цветовая тема")
        self._menus.append(theme_menu)
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for label, value in (("Как в системе", "system"), ("Светлая", "light"), ("Тёмная", "dark")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.theme_combo.currentData() == value)
            action.triggered.connect(
                lambda _checked=False, selected=value: self._set_theme(selected)
            )
            theme_group.addAction(action)
            theme_menu.addAction(action)
            self.theme_actions[value] = action
        theme_menu.addSeparator()
        for label, checkbox in (
            ("Уменьшить прозрачность", self.reduce_transparency),
            ("Повышенный контраст", self.high_contrast),
            ("Уменьшить движение", self.reduce_motion),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(checkbox.isChecked())
            action.triggered.connect(checkbox.setChecked)
            checkbox.toggled.connect(action.setChecked)
            theme_menu.addAction(action)

        window_menu = add_menu("Окно")
        minimize = QAction("Свернуть", self)
        minimize.setShortcut(QKeySequence("Meta+M" if sys.platform == "darwin" else "Ctrl+M"))
        minimize.triggered.connect(self.showMinimized)
        window_menu.addAction(minimize)
        close = QAction("Закрыть окно", self)
        close.setShortcut(QKeySequence.StandardKey.Close)
        close.triggered.connect(self.close)
        window_menu.addAction(close)

        help_menu = add_menu("Справка")
        help_about = QAction("О Study Agent…", self)
        help_about.triggered.connect(about.trigger)
        help_menu.addAction(help_about)
        self._update_edit_actions()

    def _set_theme(self, theme: str) -> None:
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme))

    def _edit_target(self) -> QWidget | None:
        target = QApplication.focusWidget()
        if isinstance(target, QComboBox) and target.isEditable():
            return target.lineEdit()
        return target

    def _update_edit_actions(self) -> None:
        target = self._edit_target()
        if target is None:
            for action in self.edit_actions.values():
                action.setEnabled(False)
            return
        is_line_edit = isinstance(target, QLineEdit)
        has_selection = isinstance(target, (QLineEdit, QLabel)) and target.hasSelectedText()
        self.edit_actions["undo"].setEnabled(is_line_edit and target.isUndoAvailable())
        self.edit_actions["redo"].setEnabled(is_line_edit and target.isRedoAvailable())
        self.edit_actions["cut"].setEnabled(is_line_edit and has_selection)
        self.edit_actions["copy"].setEnabled(has_selection)
        self.edit_actions["paste"].setEnabled(
            is_line_edit and bool(QApplication.clipboard().text())
        )
        self.edit_actions["select_all"].setEnabled(is_line_edit and bool(target.text()))

    def _edit_command(self, command: str) -> None:
        target = self._edit_target()
        if target is None:
            return
        if command == "copy" and isinstance(target, QLabel):
            if target.hasSelectedText():
                QApplication.clipboard().setText(target.selectedText())
            return
        if isinstance(target, QLineEdit):
            methods = {
                "undo": target.undo,
                "redo": target.redo,
                "cut": target.cut,
                "copy": target.copy,
                "paste": target.paste,
                "select_all": target.selectAll,
            }
            methods[command]()
            self._update_edit_actions()

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
        self.nav_symbols = ("search", "library", "settings")
        labels = ("Поиск", "Библиотека", "Настройки")
        fallback_symbols = ("⌕", "▤", "⚙")
        for index, (label, fallback) in enumerate(zip(labels, fallback_symbols, strict=True)):
            button = named(QPushButton(label), "nav")
            if sys.platform == "darwin":
                button.setIconSize(QSize(18, 18))
            else:
                button.setText(f"{fallback}   {label}")
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
        self.library_summary = named(
            QLabel("PDF, изображения, Markdown и TXT; сканы обрабатываются локально."), "muted"
        )
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
        reduce_motion_enabled = SETTINGS.value("appearance/reduce_motion", False, type=bool)
        self.reduce_transparency = AppleSwitch(
            "Уменьшить прозрачность поверхностей", reduce_motion=reduce_motion_enabled
        )
        self.reduce_transparency.setChecked(
            SETTINGS.value("appearance/reduce_transparency", False, type=bool)
        )
        self.reduce_transparency.setToolTip(
            "Использовать непрозрачные поверхности с более чёткими границами."
        )
        self.reduce_transparency.toggled.connect(self._appearance_changed)
        appearance_layout.addWidget(self.reduce_transparency)
        self.high_contrast = AppleSwitch("Повышенный контраст", reduce_motion=reduce_motion_enabled)
        self.high_contrast.setChecked(SETTINGS.value("appearance/high_contrast", False, type=bool))
        self.high_contrast.setToolTip("Усилить контраст текста, границ и клавиатурного фокуса.")
        self.high_contrast.toggled.connect(self._appearance_changed)
        appearance_layout.addWidget(self.high_contrast)
        self.reduce_motion = AppleSwitch("Уменьшить движение", reduce_motion=reduce_motion_enabled)
        self.setting_switches = (
            self.reduce_transparency,
            self.high_contrast,
            self.reduce_motion,
        )
        self.reduce_motion.setChecked(reduce_motion_enabled)
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
        for switch in self.setting_switches:
            switch.set_reduce_motion(self.reduce_motion.isChecked())
        if self.reduce_motion.isChecked() and hasattr(self, "_page_animation"):
            self._page_animation.stop()
            self._page_opacity.setOpacity(1.0)
        for theme, action in getattr(self, "theme_actions", {}).items():
            action.setChecked(self.theme_combo.currentData() == theme)
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
        tokens = tokens_for(
            self._resolved_theme(),
            reduce_transparency=self.reduce_transparency.isChecked(),
            high_contrast=self.high_contrast.isChecked(),
        )
        self.canvas.set_background_color(tokens.window)
        QApplication.instance().setStyleSheet(
            build_stylesheet(
                self._resolved_theme(),
                reduce_transparency=self.reduce_transparency.isChecked(),
                high_contrast=self.high_contrast.isChecked(),
            )
        )
        for switch in self.setting_switches:
            switch.set_colors(
                on=tokens.switch_on,
                off=tokens.switch_off,
                thumb=tokens.switch_thumb,
                border=tokens.switch_border,
                border_width=tokens.switch_border_width,
                focus=tokens.focus,
            )
        self._update_navigation_icons(tokens)

    def _update_navigation_icons(self, tokens: ThemeTokens | None = None) -> None:
        if sys.platform != "darwin":
            return
        if tokens is None:
            tokens = tokens_for(
                self._resolved_theme(),
                reduce_transparency=self.reduce_transparency.isChecked(),
                high_contrast=self.high_contrast.isChecked(),
            )
        for button, symbol in zip(self.nav_buttons, self.nav_symbols, strict=True):
            color = tokens.text if button.isChecked() else tokens.secondary
            button.setIcon(_tinted_symbol_icon(symbol, color))

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        for page, action in getattr(self, "view_actions", {}).items():
            action.setChecked(page == index)
        self._update_navigation_icons()
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
            f"{len(self.sources)} папок · {document_count} файлов"
            if self.sources
            else "PDF, изображения, Markdown и TXT; сканы обрабатываются локально."
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
        self._search_warning_text = ""
        set_status(self.search_state, "Ищу фрагменты в выбранных папках…", "progress")
        self._clear_results()

        def retrieve() -> tuple[list[SearchHit], list[SearchWarning]]:
            warnings: list[SearchWarning] = []
            hits = search_sources(
                [LocalFolderSource(path) for path in self.sources], query, warnings=warnings
            )
            return hits, warnings

        worker = Worker(retrieve)
        worker.succeeded.connect(lambda result: self._retrieved(query, *result))
        worker.failed.connect(self._search_failed)
        self._run(worker)

    def _retrieved(self, query: str, hits: list[SearchHit], warnings: list[SearchWarning]) -> None:
        warning_text = ""
        if warnings:
            names = ", ".join(sorted({warning.document_id for warning in warnings}))
            warning_text = f" Не удалось прочитать {len(warnings)} фрагм.: {names}."
        self._search_warning_text = warning_text
        if not hits:
            set_status(
                self.search_state,
                "В выбранных материалах не нашёл фрагментов по этому запросу." + warning_text,
                "warning",
            )
            self.ask_button.setEnabled(True)
            return
        set_status(
            self.search_state,
            f"Нашёл {len(hits)} релевантных фрагментов. Формирую ответ локально…{warning_text}",
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
        title = named(QPushButton(title_text), "link")
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
            f"Ответ подготовлен локально по {min(len(hits), 5)} источникам."
            + self._search_warning_text,
            "success",
        )
        self.ask_button.setEnabled(True)

    def _search_failed(self, message: str) -> None:
        set_status(self.search_state, message + getattr(self, "_search_warning_text", ""), "error")
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
