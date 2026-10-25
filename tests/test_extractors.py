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


def test_pdf_ocr_runs_only_for_pages_without_enough_text(
    tmp_path: Path, monkeypatch
) -> None:
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

    # Проверяем строго по новому контракту DTO блоков
    assert len(result) == 2
    
    assert result[0] == ExtractedBlock(
        text="A" * 80, source_type="pdf", extraction_type="digital", page_number=1
    )
    assert result[1] == ExtractedBlock(
        text="OCR text", source_type="pdf", extraction_type="ocr", page_number=2
    )
    assert ocr_calls == ["pil_image_from:"]


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
        return [ExtractedBlock(text="Recognized study notes", source_type="image", 
                               extraction_type="ocr")]

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


def test_extract_docx_paragraphs_and_tables(tmp_path: Path, monkeypatch) -> None:
    """Тестирует извлечение DOCX: проверку структуры заголовков и таблиц."""
    class FakeParagraph:
        def __init__(self, text: str, style_name: str) -> None:
            self.text = text
            self.style = SimpleNamespace(name=style_name)

    class FakeRow:
        def __init__(self, cells_text: list[str]) -> None:
            self.cells = [SimpleNamespace(text=t) for t in cells_text]

    class FakeTable:
        def __init__(self, rows_data: list[list[str]]) -> None:
            self.rows = [FakeRow(r) for r in rows_data]

    class FakeDocument:
        def __init__(self, path: Path) -> None:
            self.paragraphs = [
                FakeParagraph("Заголовок 1", "Heading 1"),
                FakeParagraph("Обычный текст с Юникодом (Привет, мир!)", "Normal"),
                FakeParagraph("   ", "Normal"),  # Пустая строка — должна игнорироваться
            ]
            self.tables = [
                FakeTable([["Ячейка 1", "Ячейка 2"], ["Ячейка 3", ""]])
            ]

    monkeypatch.setitem(
        __import__("sys").modules,
        "docx",
        SimpleNamespace(Document=FakeDocument),
    )

    result = extractors._extract_docx(tmp_path / "document.docx")

    assert len(result) == 3

    # Проверяем заголовок
    assert result[0] == ExtractedBlock(
        text="Заголовок 1", source_type="docx", extraction_type="digital",
        page_number=None, heading="Заголовок 1", marker="heading_0"
    )
    # Проверяем обычный текст, привязавшийся к заголовку, и поддержку кириллицы (Unicode)
    assert result[1] == ExtractedBlock(
        text="Обычный текст с Юникодом (Привет, мир!)", source_type="docx", 
        extraction_type="digital", page_number=None, heading="Заголовок 1", 
        marker="paragraph_1"
    )
    # Проверяем таблицу, которая тоже переняла контекст заголовка
    assert result[2] == ExtractedBlock(
        text="Ячейка 1 | Ячейка 2\nЯчейка 3", source_type="docx", extraction_type="digital",
        page_number=None, heading="Заголовок 1", marker="table_0"
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
