from study_agent.theme import build_stylesheet, tokens_for


def test_light_and_dark_tokens_have_distinct_surfaces() -> None:
    dark = tokens_for("dark", reduce_transparency=False, high_contrast=False)
    light = tokens_for("light", reduce_transparency=False, high_contrast=False)

    assert dark.window != light.window
    assert dark.text != light.text
    assert dark.content != dark.glass


def test_accessibility_options_make_surfaces_opaque_and_focus_clear() -> None:
    tokens = tokens_for("dark", reduce_transparency=True, high_contrast=True)
    stylesheet = build_stylesheet("dark", reduce_transparency=True, high_contrast=True)

    assert tokens.glass == tokens.content
    assert "border: 2px solid" in stylesheet
    assert "QListWidget:focus" in stylesheet


def test_light_stylesheet_uses_light_surface_tokens() -> None:
    stylesheet = build_stylesheet("light")

    assert "QMainWindow { background: #eef1f5; }" in stylesheet
    assert "QFrame#glass { background-color: #f8f9fb;" in stylesheet
