"""Shared brand and semantic color tokens for the Study Agent interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    window: str
    content: str
    card: str
    sidebar: str
    sidebar_hover: str
    edge: str
    control_edge: str
    text: str
    secondary: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    link: str
    field: str
    selection: str
    focus: str
    separator: str
    success: str
    warning: str
    error: str
    progress: str
    brand_bright: str
    brand_sky: str
    brand_ice: str
    brand_pale: str
    brand_cloud: str


_DARK = ThemeTokens(
    window="#101C2E",
    content="#101C2E",
    card="#1B2B43",
    sidebar="#16263B",
    sidebar_hover="#203956",
    edge="#334966",
    control_edge="#617B99",
    text="#F5F9FF",
    secondary="#A8BBD1",
    muted="#A8BBD1",
    accent="#0B65F2",
    accent_hover="#095BD9",
    accent_text="#FFFFFF",
    link="#6FB7FF",
    field="#1B2B43",
    selection="#203956",
    focus="#6FB7FF",
    separator="#334966",
    success="#77D6A0",
    warning="#F4C56A",
    error="#FF8A80",
    progress="#6FB7FF",
    brand_bright="#2589FC",
    brand_sky="#6FB7FF",
    brand_ice="#9FD7FC",
    brand_pale="#C3DCF9",
    brand_cloud="#D8ECFD",
)

_LIGHT = ThemeTokens(
    window="#F7FAFF",
    content="#F7FAFF",
    card="#FFFFFF",
    sidebar="#FFFFFF",
    sidebar_hover="#E7F3FF",
    edge="#C3DCF9",
    control_edge="#60758F",
    text="#101C2E",
    secondary="#60758F",
    muted="#60758F",
    accent="#0B65F2",
    accent_hover="#095BD9",
    accent_text="#FFFFFF",
    link="#0B65F2",
    field="#FFFFFF",
    selection="#E7F3FF",
    focus="#0B65F2",
    separator="#C3DCF9",
    success="#167A4A",
    warning="#8A5A00",
    error="#B42318",
    progress="#0B65F2",
    brand_bright="#2589FC",
    brand_sky="#50A2FD",
    brand_ice="#9FD7FC",
    brand_pale="#C3DCF9",
    brand_cloud="#D8ECFD",
)


def tokens_for(mode: str, *, reduce_transparency: bool, high_contrast: bool) -> ThemeTokens:
    """Return a complete light/dark palette with accessible display variants."""
    base = _LIGHT if mode == "light" else _DARK
    if reduce_transparency:
        base = ThemeTokens(**{**base.__dict__, "sidebar": base.content})
    if high_contrast:
        return ThemeTokens(
            **{
                **base.__dict__,
                "edge": base.text,
                "control_edge": base.text,
                "secondary": base.text,
                "muted": base.text,
                "focus": base.accent,
                "separator": base.text,
            }
        )
    return base


def build_stylesheet(
    mode: str, *, reduce_transparency: bool = False, high_contrast: bool = False
) -> str:
    """Build the shared Qt stylesheet from semantic color tokens."""
    t = tokens_for(mode, reduce_transparency=reduce_transparency, high_contrast=high_contrast)
    edge_width = 2 if high_contrast else 1
    return f"""
* {{ color: {t.text}; }}
QMainWindow {{ background: {t.window}; }}
QWidget#canvas {{ background: {t.window}; }}
QFrame#content {{ background-color: {t.content}; border: {edge_width}px solid {t.edge};
  border-radius: 20px; }}
QFrame#card {{ background-color: {t.card}; border: 1px solid {t.separator}; border-radius: 14px; }}
QFrame#sidebar {{ background-color: {t.sidebar}; border: {edge_width}px solid {t.edge};
  border-radius: 22px; }}
QLabel#brand {{ font-size: 17px; font-weight: 650; }}
QLabel#title {{ font-size: 30px; font-weight: 650; }}
QLabel#subtitle {{ color: {t.secondary}; font-size: 14px; }}
QLabel#muted {{ color: {t.muted}; }}
QLabel#eyebrow {{ color: {t.secondary}; font-size: 12px; font-weight: 650; }}
QLabel#status[state="success"] {{ color: {t.success}; }}
QLabel#status[state="warning"] {{ color: {t.warning}; }}
QLabel#status[state="error"] {{ color: {t.error}; }}
QLabel#status[state="progress"] {{ color: {t.progress}; }}
QPushButton {{ background: {t.card}; border: 1px solid {t.control_edge}; border-radius: 11px;
  padding: 10px 14px; font-size: 14px; }}
QPushButton:hover {{ background: {t.sidebar_hover}; }}
QPushButton:pressed {{ background: {t.selection}; }}
QPushButton:disabled {{ color: {t.muted}; background: {t.content}; }}
QPushButton#primary {{ background: {t.accent}; color: {t.accent_text}; border: 0;
  font-weight: 650; }}
QPushButton#primary:hover {{ background: {t.accent_hover}; color: {t.accent_text}; }}
QPushButton#nav {{ text-align: left; padding: 12px 14px; background: transparent;
  border: 1px solid transparent; color: {t.secondary}; }}
QPushButton#nav:hover {{ background: {t.sidebar_hover}; }}
QPushButton#nav:checked {{ background: {t.selection}; color: {t.text};
  border: 1px solid {t.edge}; }}
QPushButton#link {{ background: transparent; border: 0; color: {t.link};
  text-align: left; padding: 2px; }}
QLineEdit, QTextEdit, QComboBox {{ background: {t.field}; border: 1px solid {t.control_edge};
  border-radius: 11px; padding: 10px 12px; selection-background-color: {t.selection}; }}
QLineEdit::placeholder {{ color: {t.muted}; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
  background: {t.field}; border: 1px solid {t.control_edge}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border: 1px solid {t.focus}; }}
QCheckBox::indicator:disabled {{ background: {t.content}; border: 1px solid {t.separator}; }}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox QAbstractItemView {{ background: {t.card}; border: 1px solid {t.control_edge};
  selection-background-color: {t.selection}; }}
QListWidget {{ background: transparent; border: 0; }}
QListWidget::item {{ background: {t.card}; border: 1px solid {t.separator};
  border-radius: 11px; margin: 3px 0; padding: 11px; }}
QListWidget::item:selected {{ background: {t.selection}; color: {t.text}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {t.muted}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QProgressBar {{ background: {t.content}; border: 1px solid {t.edge}; border-radius: 4px;
  text-align: center; }}
QProgressBar::chunk {{ background: {t.progress}; border-radius: 3px; }}
QToolTip {{ background: {t.card}; color: {t.text}; border: 1px solid {t.edge}; }}
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QCheckBox:focus,
QListWidget:focus {{ border: {edge_width}px solid {t.focus}; }}
"""
