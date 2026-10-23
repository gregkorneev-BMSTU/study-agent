from itertools import product

from study_agent.theme import build_stylesheet, tokens_for


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    weights = (0.2126, 0.7152, 0.0722)
    return sum(weight * channel for weight, channel in zip(weights, linear, strict=True))


def _contrast(foreground: str, background: str) -> float:
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_brand_and_surface_tokens_match_approved_palette() -> None:
    light = tokens_for("light", reduce_transparency=False, high_contrast=False)
    dark = tokens_for("dark", reduce_transparency=False, high_contrast=False)

    assert (light.accent, light.brand_bright, light.brand_sky) == (
        "#0B65F2",
        "#2589FC",
        "#50A2FD",
    )
    assert (light.window, light.card, light.text, light.secondary, light.edge, light.selection) == (
        "#F7FAFF",
        "#FFFFFF",
        "#101C2E",
        "#60758F",
        "#C3DCF9",
        "#E7F3FF",
    )
    assert (dark.window, dark.card, dark.text, dark.secondary, dark.edge, dark.selection) == (
        "#101C2E",
        "#1B2B43",
        "#F5F9FF",
        "#A8BBD1",
        "#334966",
        "#203956",
    )
    assert dark.brand_sky == "#6FB7FF"


def test_text_and_semantic_states_meet_wcag_aa_on_content_surfaces() -> None:
    for mode, foregrounds in (
        (
            "light",
            ("text", "secondary", "link", "success", "warning", "error", "progress"),
        ),
        (
            "dark",
            ("text", "secondary", "link", "success", "warning", "error", "progress"),
        ),
    ):
        tokens = tokens_for(mode, reduce_transparency=False, high_contrast=False)
        for foreground_name, background in product(foregrounds, (tokens.window, tokens.card)):
            assert _contrast(getattr(tokens, foreground_name), background) >= 4.5, (
                mode,
                foreground_name,
                background,
            )
        assert _contrast(tokens.accent_text, tokens.accent) >= 4.5
        assert _contrast(tokens.accent_text, tokens.accent_hover) >= 4.5
        assert _contrast(tokens.text, tokens.selection) >= 4.5
        assert _contrast(tokens.focus, tokens.field) >= 3
        assert _contrast(tokens.control_edge, tokens.field) >= 3


def test_semantic_states_are_not_brand_blue() -> None:
    for mode in ("light", "dark"):
        tokens = tokens_for(mode, reduce_transparency=False, high_contrast=False)
        assert tokens.error not in (tokens.accent, tokens.brand_bright, tokens.brand_sky)
        assert tokens.warning not in (tokens.accent, tokens.brand_bright, tokens.brand_sky)


def test_accessibility_options_make_sidebar_opaque_and_focus_clear() -> None:
    tokens = tokens_for("dark", reduce_transparency=True, high_contrast=True)
    stylesheet = build_stylesheet("dark", reduce_transparency=True, high_contrast=True)

    assert tokens.sidebar == tokens.content
    assert tokens.control_edge == tokens.text
    assert "border: 2px solid" in stylesheet
    assert "QListWidget:focus" in stylesheet
    assert "QCheckBox::indicator:checked" in stylesheet
    assert "QCheckBox:focus" in stylesheet
    assert "QLabel#status[state=\"error\"]" in stylesheet


def test_light_stylesheet_uses_shared_brand_tokens_and_existing_components() -> None:
    stylesheet = build_stylesheet("light")

    assert "QMainWindow { background: #F7FAFF; }" in stylesheet
    assert "QFrame#card { background-color: #FFFFFF;" in stylesheet
    assert "QPushButton#primary { background: #0B65F2; color: #FFFFFF;" in stylesheet
    assert "QProgressBar::chunk { background: #0B65F2;" in stylesheet
    assert "QPushButton:hover" in stylesheet
    assert "QPushButton:pressed" in stylesheet
    assert "QPushButton:disabled" in stylesheet
    assert "QLineEdit:focus" in stylesheet
