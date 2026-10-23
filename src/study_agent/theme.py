"""Visual tokens for the Study Agent desktop interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    window: str
    content: str
    card: str
    glass: str
    glass_hover: str
    edge: str
    text: str
    secondary: str
    muted: str
    accent: str
    accent_text: str
    field: str
    selection: str
    focus: str
    separator: str


_DARK = ThemeTokens(
    window="#171a20",
    content="#20242c",
    card="#252a33",
    glass="rgba(40, 46, 57, 226)",
    glass_hover="rgba(65, 73, 88, 244)",
    edge="rgba(255, 255, 255, 20)",
    text="#f4f5f8",
    secondary="#c4cad4",
    muted="#a3acba",
    accent="#b8d5ff",
    accent_text="#15253b",
    field="#191d24",
    selection="#38547a",
    focus="#88b8ff",
    separator="#373d48",
)

_LIGHT = ThemeTokens(
    window="#eef1f5",
    content="#f8f9fb",
    card="#ffffff",
    glass="rgba(255, 255, 255, 230)",
    glass_hover="rgba(255, 255, 255, 250)",
    edge="rgba(26, 38, 56, 30)",
    text="#18202b",
    secondary="#424d5d",
    muted="#566273",
    accent="#275d9e",
    accent_text="#ffffff",
    field="#ffffff",
    selection="#c9ddf6",
    focus="#1769c2",
    separator="#d9dee6",
)


def tokens_for(mode: str, *, reduce_transparency: bool, high_contrast: bool) -> ThemeTokens:
    """Return light/dark tokens, with accessible opaque and contrast variants."""
    base = _LIGHT if mode == "light" else _DARK
    if reduce_transparency:
        base = ThemeTokens(
            **{
                **base.__dict__,
                "glass": base.content,
                "glass_hover": base.card,
                "edge": base.separator,
            }
        )
    if high_contrast:
        return ThemeTokens(
            **{
                **base.__dict__,
                "edge": base.text,
                "secondary": base.text,
                "muted": base.secondary,
                "focus": base.accent,
                "separator": base.text,
            }
        )
    return base


def build_stylesheet(
    mode: str, *, reduce_transparency: bool = False, high_contrast: bool = False
) -> str:
    """Build the shared Qt stylesheet from the visual tokens."""
    t = tokens_for(mode, reduce_transparency=reduce_transparency, high_contrast=high_contrast)
    edge_width = 2 if high_contrast else 1
    glass_fill = t.content if reduce_transparency else t.glass
    return f"""
* {{ color: {t.text}; }}
QMainWindow {{ background: {t.window}; }}
QWidget#canvas {{ background: {t.window}; }}
QFrame#glass {{ background-color: {t.content}; border: {edge_width}px solid {t.edge};
  border-radius: 20px; }}
QFrame#card {{ background-color: {t.card}; border: 1px solid {t.separator}; border-radius: 14px; }}
QFrame#sidebar {{ background-color: {glass_fill}; border: {edge_width}px solid {t.edge};
  border-radius: 22px; }}
QLabel#brand {{ font-size: 19px; font-weight: 650; }}
QLabel#title {{ font-size: 30px; font-weight: 650; }}
QLabel#subtitle {{ color: {t.secondary}; font-size: 14px; }}
QLabel#muted {{ color: {t.muted}; }}
QLabel#eyebrow {{ color: {t.secondary}; font-size: 12px; font-weight: 650; }}
QPushButton {{ background: {t.card}; border: 1px solid {t.edge}; border-radius: 11px;
  padding: 10px 14px; font-size: 14px; }}
QPushButton:hover {{ background: {t.glass_hover}; }}
QPushButton:pressed {{ background: {t.selection}; }}
QPushButton:disabled {{ color: {t.muted}; background: {t.content}; }}
QPushButton#primary {{ background: {t.accent}; color: {t.accent_text}; border: 0;
  font-weight: 650; }}
QPushButton#primary:hover {{ background: {t.focus}; color: {t.accent_text}; }}
QPushButton#nav {{ text-align: left; padding: 12px 14px; background: transparent;
  border: 1px solid transparent; color: {t.secondary}; }}
QPushButton#nav:hover {{ background: {t.glass_hover}; }}
QPushButton#nav:checked {{ background: {t.selection}; color: {t.text};
  border: 1px solid {t.edge}; }}
QPushButton#link {{ background: transparent; border: 0; color: {t.accent};
  text-align: left; padding: 2px; }}
QLineEdit, QTextEdit, QComboBox {{ background: {t.field}; border: 1px solid {t.edge};
  border-radius: 11px; padding: 10px 12px; selection-background-color: {t.selection}; }}
QLineEdit::placeholder {{ color: {t.muted}; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
  background: {t.field}; border: 1px solid {t.edge}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border: 1px solid {t.focus}; }}
QCheckBox::indicator:disabled {{ background: {t.content}; border: 1px solid {t.separator}; }}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox QAbstractItemView {{ background: {t.card}; border: 1px solid {t.edge};
  selection-background-color: {t.selection}; }}
QListWidget {{ background: transparent; border: 0; }}
QListWidget::item {{ background: {t.card}; border: 1px solid {t.separator};
  border-radius: 11px; margin: 3px 0; padding: 11px; }}
QListWidget::item:selected {{ background: {t.selection}; color: {t.text}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {t.muted}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QCheckBox:focus,
QListWidget:focus {{ border: {edge_width}px solid {t.focus}; }}
"""
