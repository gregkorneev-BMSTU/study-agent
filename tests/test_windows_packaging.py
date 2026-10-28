from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def test_windows_backend_archive_contains_executable_runtime_and_notices(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "StudyAgentBackend"
    (source / "_internal").mkdir(parents=True)
    (source / "StudyAgentBackend.exe").write_bytes(b"synthetic executable")
    (source / "_internal" / "runtime.dll").write_bytes(b"synthetic runtime")
    archive = tmp_path / "StudyAgentBackend.zip"

    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "package_windows_backend.py"),
            str(source),
            str(archive),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(archive) as package:
        assert package.read("StudyAgentBackend.exe") == b"synthetic executable"
        assert package.read("_internal/runtime.dll") == b"synthetic runtime"
        assert package.read("Legal/LICENSE") == (root / "LICENSE").read_bytes()
        notices = package.read("Legal/THIRD_PARTY_NOTICES.md")
        assert notices == (root / "THIRD_PARTY_NOTICES.md").read_bytes()


def test_windows_backend_archive_preserves_colliding_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "package_windows_backend.py"
    spec = importlib.util.spec_from_file_location("package_windows_backend", script)
    assert spec is not None and spec.loader is not None
    package_windows_backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package_windows_backend)
    source = tmp_path / "backend"
    source.mkdir()
    (source / "StudyAgentBackend.exe").write_bytes(b"synthetic executable")
    notices = tmp_path / "notices"
    for folder, name, content in (("one", "LICENSE", "first"), ("two", "license", "second")):
        (notices / folder).mkdir(parents=True)
        (notices / folder / name).write_text(content)

    class Distribution:
        metadata = {"Name": "example"}
        files = [Path("one/LICENSE"), Path("two/license")]

        def locate_file(self, item: Path) -> Path:
            return notices / item

    archive = tmp_path / "backend.zip"
    monkeypatch.setattr(sys, "argv", ["package_windows_backend.py", str(source), str(archive)])
    monkeypatch.setattr(package_windows_backend.metadata, "distributions", lambda: [Distribution()])
    assert package_windows_backend.main() == 0

    with zipfile.ZipFile(archive) as package:
        names = [name for name in package.namelist() if name.startswith("Legal/packages/example/")]
        assert len(names) == len({name.casefold() for name in names}) == 2
        assert {package.read(name).decode() for name in names} == {"first", "second"}
        package.extractall(tmp_path / "extracted")
