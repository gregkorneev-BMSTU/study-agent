import sys
from pathlib import Path

from study_agent.ui import _brand_logo_path, _sf_symbol_path


def test_brand_logo_resolves_from_icon_kit() -> None:
    logo = _brand_logo_path()

    assert logo.is_file()
    assert logo.name == "AppIcon_1024.png"


def test_brand_logo_resolves_from_macos_bundle_resources(
    tmp_path: Path, monkeypatch
) -> None:
    logo = tmp_path / "Contents" / "Resources" / "study_agent" / "assets" / "AppIcon_1024.png"
    logo.parent.mkdir(parents=True)
    logo.touch()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "Contents" / "Frameworks"), raising=False)

    assert _brand_logo_path() == logo


def test_sf_symbol_assets_are_packaged() -> None:
    for name in ("search", "library", "settings"):
        asset = _sf_symbol_path(name)
        assert asset.is_file()
