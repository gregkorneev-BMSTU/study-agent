from pathlib import Path
from types import SimpleNamespace

from study_agent import extractors
from study_agent.models import ExtractedBlock
from study_agent.sources import LocalFolderSource


def test_local_source_lists_supported_files(tmp_path: Path) -> None:
    """Проверяет, что list_documents видит все форматы, включая новый .docx."""
    (tmp_path / "scan.pdf").write_bytes(b"pdf")
    (tmp_path / "handwritten.png").write_bytes(b"image")
    (tmp_path / "notes.txt").write_text("Text", encoding="utf-8")
    (tmp_path / "document.docx").write_bytes(b"docx")  # Добавили проверку DOCX

    assert [doc.document_id for doc in LocalFolderSource(tmp_path).list_documents()] == [
        "document.docx",
        "handwritten.png",
        "notes.txt",
        "scan.pdf",
    ]


def test_pdf_ocr_runs_only_for_pages_without_enough_text(tmp_path: Path, monkeypatch) -> None:
    """Проверяет разбиение PDF по страницам и ленивый вызов OCR."""

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
            # Возвращаем объект с методом to_pil(), имитирующим PIL Image
            return SimpleNamespace(to_pil=lambda: f"pil_image_from:{self.text}")

        def close(self) -> None:
            pass

    class PdfDocument:
        def __init__(self, path: Path) -> None:
            self.pages = [
                Page("A" * 80),
                Page(""),
                Page("Дисциплина: математика. " + "Èíòåãðàëû è óðàâíåíèÿ " * 4),
            ]

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

    # Проверяем строго по новому контракту DTO блоков
    assert len(result) == 3

    assert result[0] == ExtractedBlock(
        text="A" * 80, source_type="pdf", extraction_type="digital", page_number=1
    )
    assert result[1] == ExtractedBlock(
        text="OCR text", source_type="pdf", extraction_type="ocr", page_number=2
    )
    assert result[2] == ExtractedBlock(
        text="OCR text", source_type="pdf", extraction_type="ocr", page_number=3
    )
    assert ocr_calls == [
        "pil_image_from:",
        "pil_image_from:Дисциплина: математика. " + "Èíòåãðàëû è óðàâíåíèÿ " * 4,
    ]


def test_ocr_result_is_cached_as_json_outside_source_folder(tmp_path: Path, monkeypatch) -> None:
    """Проверяет работу нового изолированного JSON-кэша."""
    image = tmp_path / "scan.png"
    image.write_bytes(b"synthetic image")
    cache_root = tmp_path / "application-cache"

    # Мокаем кэш-путь с новым расширением .json
    monkeypatch.setattr(extractors, "_cache_path", lambda path: cache_root / "result.json")
    calls = 0

    def fake_extract(path: Path) -> list[ExtractedBlock]:
        nonlocal calls
        calls += 1
        return [
            ExtractedBlock(
                text="Recognized study notes", source_type="image", extraction_type="ocr"
            )
        ]

    monkeypatch.setattr(extractors, "_extract_image", fake_extract)
    source = LocalFolderSource(tmp_path)

    expected_blocks = [
        ExtractedBlock(text="Recognized study notes", source_type="image", extraction_type="ocr")
    ]

    # Первый вызов — парсит, второй — берет из JSON-кэша
    assert source.read("scan.png") == expected_blocks
    assert source.read("scan.png") == expected_blocks
    assert calls == 1
    assert (cache_root / "result.json").is_file()


def test_extract_docx_paragraphs_and_tables(tmp_path: Path) -> None:
    """Real DOCX XML order, nested heading context and searchable table text."""
    import docx

    document = docx.Document()
    document.add_heading("Chapter A", level=1)
    document.add_paragraph("paragraph A")
    document.add_table(rows=1, cols=2).rows[0].cells[0].text = "table A"
    document.add_heading("Section B", level=2)
    document.add_paragraph("paragraph B")
    document.add_table(rows=1, cols=2).rows[0].cells[0].text = "table B"
    document.add_heading("Chapter C", level=1)
    document.add_paragraph("paragraph C")
    path = tmp_path / "document.docx"
    document.save(path)

    result = extractors.extract_document(path)
    assert [block.text for block in result] == [
        "Chapter A",
        "paragraph A",
        "table A",
        "Section B",
        "paragraph B",
        "table B",
        "Chapter C",
        "paragraph C",
    ]
    assert [block.heading for block in result] == [
        "Chapter A",
        "Chapter A",
        "Chapter A",
        "Chapter A › Section B",
        "Chapter A › Section B",
        "Chapter A › Section B",
        "Chapter C",
        "Chapter C",
    ]
    assert len({block.marker for block in result}) == len(result)
    from study_agent.indexer import DocumentIndexer
    from study_agent.search import search_sources
    from study_agent.storage import IndexStorage

    source = LocalFolderSource(tmp_path)
    storage = IndexStorage(tmp_path / "index.sqlite3")
    DocumentIndexer(storage).sync_source(source)

    assert (
        search_sources([source], "table B", storage=storage)[0].document_id == "document.docx"
    )


def test_corrupted_or_empty_docx_does_not_block(tmp_path: Path, monkeypatch) -> None:
    """Проверяет, что битый DOCX возвращает варнинг и не рушит пайплайн."""

    def fake_corrupted_document(path: Path):
        raise Exception("ZipBomb or Corrupted XML")

    monkeypatch.setitem(
        __import__("sys").modules,
        "docx",
        SimpleNamespace(Document=fake_corrupted_document),
    )

    result = extractors._extract_docx(tmp_path / "broken.docx")

    assert len(result) == 1
    assert result[0].text == ""
    assert "Failed to open DOCX file" in result[0].warnings[0]


def test_plain_text_does_not_use_ocr_cache(tmp_path: Path, monkeypatch) -> None:
    def unexpected_cache(path: Path) -> Path:
        raise AssertionError(f"cache requested for {path}")

    monkeypatch.setattr(extractors, "_cache_path", unexpected_cache)
    for suffix in ("txt", "md"):
        path = tmp_path / f"notes.{suffix}"
        path.write_text("same content", encoding="utf-8")
        first = extractors.extract_document(path)
        assert first == extractors.extract_document(path)
        assert first[0].text == "same content"


def test_cache_write_failure_keeps_result_and_cleans_temp(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"first")
    cache = tmp_path / "cache" / "scan.json"
    monkeypatch.setattr(extractors, "_cache_path", lambda path: cache)
    monkeypatch.setattr(
        extractors,
        "_extract_image",
        lambda path: [
            ExtractedBlock(text="recognized", source_type="image", extraction_type="ocr")
        ],
    )
    original_replace = Path.replace

    def failed_replace(path: Path, target: Path) -> Path:
        if path.suffix == ".tmp":
            raise OSError("disk unavailable")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", failed_replace)
    assert extractors.extract_document(image)[0].text == "recognized"
    assert list(cache.parent.glob("*.tmp")) == []


def test_image_cache_invalidates_on_content_change(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"first")
    cache_dir = tmp_path / "cache"
    original_cache_path = extractors._cache_path
    monkeypatch.setattr(
        extractors, "_cache_path", lambda path: cache_dir / original_cache_path(path).name
    )
    calls: list[str] = []

    def fake_extract(path: Path) -> list[ExtractedBlock]:
        calls.append(path.read_bytes().decode())
        return [ExtractedBlock(text=calls[-1], source_type="image", extraction_type="ocr")]

    monkeypatch.setattr(extractors, "_extract_image", fake_extract)
    assert extractors.extract_document(image) == extractors.extract_document(image)
    image.write_bytes(b"second")
    assert extractors.extract_document(image)[0].text == "second"
    assert calls == ["first", "second"]


def test_pdf_cache_invalidates_on_content_change(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"first")
    cache_dir = tmp_path / "cache"
    original_cache_path = extractors._cache_path
    monkeypatch.setattr(
        extractors, "_cache_path", lambda path: cache_dir / original_cache_path(path).name
    )
    calls: list[str] = []

    def fake_extract(path: Path) -> list[ExtractedBlock]:
        calls.append(path.read_bytes().decode())
        return [ExtractedBlock(text=calls[-1], source_type="pdf", extraction_type="digital")]

    monkeypatch.setattr(extractors, "_extract_pdf", fake_extract)
    assert extractors.extract_document(pdf) == extractors.extract_document(pdf)
    pdf.write_bytes(b"second")
    assert extractors.extract_document(pdf)[0].text == "second"
    assert calls == ["first", "second"]
