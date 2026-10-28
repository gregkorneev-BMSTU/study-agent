from __future__ import annotations

import re
import sys
import zipfile
from importlib import metadata
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: package_windows_backend.py <onedir> <archive>")
    source = Path(sys.argv[1]).resolve()
    archive = Path(sys.argv[2]).resolve()
    executable = source / "StudyAgentBackend.exe"
    if not executable.is_file():
        raise SystemExit(f"required file missing: {executable}")
    repo = Path(__file__).resolve().parents[1]
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
        allowZip64=True,
    ) as output:
        used_legal_names: set[str] = set()
        for path in sorted(source.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(source).as_posix())
        output.write(repo / "LICENSE", "Legal/LICENSE")
        output.write(repo / "THIRD_PARTY_NOTICES.md", "Legal/THIRD_PARTY_NOTICES.md")
        for distribution in metadata.distributions():
            name = distribution.metadata.get("Name", "unknown")
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
            for item in distribution.files or ():
                basename = Path(str(item)).name
                if not re.search(
                    r"^(license|licence|notice|copying)(\.|$)", basename, re.IGNORECASE
                ):
                    continue
                try:
                    file = Path(distribution.locate_file(item))
                    if file.is_file():
                        prefix = f"Legal/packages/{safe_name}"
                        target = f"{prefix}/{basename}"
                        suffix = 1
                        while target.casefold() in used_legal_names:
                            target = f"{prefix}/{suffix}/{basename}"
                            suffix += 1
                        used_legal_names.add(target.casefold())
                        output.write(file, target)
                except OSError:
                    continue
    with zipfile.ZipFile(archive) as packaged:
        names = set(packaged.namelist())
        required = {"StudyAgentBackend.exe", "Legal/LICENSE", "Legal/THIRD_PARTY_NOTICES.md"}
        missing = required - names
        if missing:
            raise SystemExit(f"archive is incomplete: missing {', '.join(sorted(missing))}")
    print(f"Created {archive} ({archive.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
