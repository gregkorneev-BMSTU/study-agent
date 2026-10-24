#!/usr/bin/env python3
"""Copy project and runtime license texts into a packaged macOS app."""

from __future__ import annotations

import csv
import importlib.metadata
import shutil
import sys
from pathlib import Path, PurePosixPath

REQUIRED_LICENSES = {"pypdfium2"}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: copy_distribution_licenses.py PROJECT_ROOT LEGAL_DIR")

    project_root, legal_dir = map(Path, sys.argv[1:])
    legal_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(project_root / filename, legal_dir / filename)

    missing: list[str] = []
    inventory_path = legal_dir / "PYTHON_BUILD_ENVIRONMENT.csv"
    with inventory_path.open("w", encoding="utf-8", newline="") as inventory_file:
        inventory = csv.writer(inventory_file)
        inventory.writerow(("distribution", "version", "declared_license", "license_files_copied"))
        distributions = sorted(
            (
                item
                for item in importlib.metadata.distributions()
                if (item.metadata.get("Name") or "").lower().replace("_", "-")
                != "study-agent"
            ),
            key=lambda item: (item.metadata.get("Name") or "").lower(),
        )
        for distribution in distributions:
            name = distribution.metadata.get("Name", "unknown")
            version = distribution.version
            normalized_name = name.lower().replace("_", "-")
            destination = legal_dir / f"{name}-{version}"
            copied = 0
            for item in distribution.files or ():
                parts = PurePosixPath(str(item)).parts
                is_dist_info = any(part.lower().endswith(".dist-info") for part in parts)
                try:
                    if is_dist_info:
                        license_index = next(
                            i for i, part in enumerate(parts) if part.lower() == "licenses"
                        )
                        relative = Path(*parts[license_index + 1 :])
                    else:
                        license_index = next(
                            i
                            for i, part in enumerate(parts)
                            if part.upper() == "BUILD_LICENSES"
                        )
                        relative = Path(*parts[license_index + 1 :])
                except StopIteration:
                    filename = parts[-1].lower() if parts else ""
                    if not is_dist_info or not filename.startswith(
                        ("license", "licence", "copying", "notice")
                    ):
                        continue
                    relative = Path(filename)
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied += 1
            declared_license = (
                distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License")
                or "unspecified in package metadata"
            )
            inventory.writerow((name, version, declared_license, copied))
            if normalized_name in REQUIRED_LICENSES and copied == 0:
                missing.append(name)

    if missing:
        raise SystemExit(
            "Missing package license files for: " + ", ".join(missing)
            + ". Reinstall the packaging dependencies before building the app."
        )

    python_license = None
    for parent in Path(sys.executable).resolve().parents:
        for filename in ("LICENSE", "LICENSE.txt", "LICENSE.rtf"):
            candidate = parent / filename
            if candidate.is_file() and "Python Software Foundation" in candidate.read_text(
                errors="ignore"
            ):
                python_license = candidate
                break
        if python_license:
            break
    if python_license is None:
        raise SystemExit("Could not locate the Python runtime's PSF license file.")
    shutil.copy2(python_license, legal_dir / f"Python-LICENSE{python_license.suffix}")


if __name__ == "__main__":
    main()
