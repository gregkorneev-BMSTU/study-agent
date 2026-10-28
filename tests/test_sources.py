from pathlib import Path

import pytest

from study_agent.models import (
    ExtractedBlock,  # Шаг исправления: импортируем новый общий контракт данных
)
from study_agent.sources import LocalFolderSource


def test_lists_supported_formats_and_reads_text_files(tmp_path: Path) -> None:
    (tmp_path / "week-1").mkdir()
    (tmp_path / "week-1" / "notes.md").write_text("# Notes", encoding="utf-8")
    (tmp_path / "summary.TXT").write_text("Summary", encoding="utf-8")
    (tmp_path / "slides.pdf").write_bytes(b"not indexed yet")

    source = LocalFolderSource(tmp_path)

    documents = source.list_documents()
    assert [document.document_id for document in documents] == [
        "slides.pdf",
        "summary.TXT",
        "week-1/notes.md",
    ]
    
    # Шаг исправления: проверяем, что вернулся список DTO-блоков с правильным содержимым
    result = source.read("week-1/notes.md")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == ExtractedBlock(
        text="# Notes",
        source_type="markdown",
        extraction_type="digital",
        heading="Notes",
        marker="line:1",
    )


def test_rejects_paths_outside_root(tmp_path: Path) -> None:
    source = LocalFolderSource(tmp_path)

    with pytest.raises(ValueError, match="relative path"):
        source.read("../outside.txt")


def test_does_not_follow_file_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(outside)
    source = LocalFolderSource(tmp_path)

    assert source.list_documents() == []
    with pytest.raises(ValueError, match="supported regular file"):
        source.read("linked.txt")


def test_requires_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalFolderSource(tmp_path / "missing")
