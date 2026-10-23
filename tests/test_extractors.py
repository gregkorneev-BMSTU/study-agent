from pathlib import Path
from types import SimpleNamespace

from study_agent import extractors
from study_agent.sources import LocalFolderSource


def test_local_source_lists_pdf_and_image_files(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(b"pdf")
    (tmp_path / "handwritten.png").write_bytes(b"image")
    (tmp_path / "notes.txt").write_text("Text", encoding="utf-8")

    assert [doc.document_id for doc in LocalFolderSource(tmp_path).list_documents()] == [
        "handwritten.png",
        "notes.txt",
        "scan.pdf",
    ]


def test_pdf_ocr_runs_only_for_pages_without_enough_text(
    tmp_path: Path, monkeypatch
) -> None:
    class TextPage:
        def __init__(self, text: str) -> None:
            self.text = text

        def get_text_range(self) -> str:
            return self.text

        def close(self) -> None:
            pass

    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def get_textpage(self) -> TextPage:
            return TextPage(self.text)

        def render(self, scale: int) -> SimpleNamespace:
            assert scale == 2
            return SimpleNamespace(to_pil=lambda: f"page:{self.text}")

        def close(self) -> None:
            pass

    class PdfDocument:
        def __init__(self, path: Path) -> None:
            self.pages = [Page("A" * 80), Page("")]

        def __iter__(self):
            return iter(self.pages)

        def close(self) -> None:
            pass

    monkeypatch.setitem(
        __import__("sys").modules,
        "pypdfium2",
        SimpleNamespace(PdfDocument=PdfDocument),
    )
    ocr_calls: list[str] = []
    def fake_ocr(image: str) -> str:
        ocr_calls.append(image)
        return "OCR text"

    monkeypatch.setattr(extractors, "_ocr_image", fake_ocr)

    result = extractors._extract_pdf(tmp_path / "scan.pdf")

    assert result == "## Page 1\n\n" + "A" * 80 + "\n\n## Page 2\n\nOCR text"
    assert ocr_calls == ["page:"]


def test_ocr_result_is_cached_outside_source_folder(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"synthetic image")
    cache_root = tmp_path / "application-cache"
    monkeypatch.setattr(extractors, "_cache_path", lambda path: cache_root / "result.md")
    calls = 0

    def fake_extract(path: Path) -> str:
        nonlocal calls
        calls += 1
        return "Recognized study notes"

    monkeypatch.setattr(extractors, "_extract_image", fake_extract)
    source = LocalFolderSource(tmp_path)

    assert source.read("scan.png") == "Recognized study notes"
    assert source.read("scan.png") == "Recognized study notes"
    assert calls == 1
    assert (cache_root / "result.md").is_file()
