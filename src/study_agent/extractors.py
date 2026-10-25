"""Local text extraction with lazy Chandra OCR for scans and images."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from study_agent.models import ExtractedBlock
from study_agent.ocr_model import model_directory, model_is_installed

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
OCR_SUFFIXES = {".pdf", *IMAGE_SUFFIXES}
_manager: Any | None = None


def extract_document(path: Path) -> list[ExtractedBlock]:
    """Extract document blocks; use local Chandra only when a page needs OCR."""
    suffix = path.suffix.lower()

    cache_path = _cache_path(path)  # Check whether cache exists
    if cache_path.is_file():
        try:
            cached_data = json.loads(cache_path.read_text(encoding="utf-8"))
            return [ExtractedBlock(**block) for block in cached_data]
        except Exception:
            pass

    blocks: list[ExtractedBlock] = []

    if suffix == ".pdf":
        blocks = _extract_pdf(path)
    elif suffix == ".docx":
        blocks = _extract_docx(path)
    elif suffix in IMAGE_SUFFIXES:
        blocks = _extract_image(path)
    else:
        text = path.read_text(encoding="utf-8")
        blocks = [ExtractedBlock(text=text, source_type="text", extraction_type="digital")]

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = cache_path.with_name(f"{cache_path.stem}.{uuid.uuid4().hex}.tmp")

        serialized_blocks = [block.to_dict() for block in blocks]

        json_data = json.dumps(serialized_blocks, ensure_ascii=False, indent=2)
        temporary.write_text(json_data, encoding="utf-8")
        temporary.replace(cache_path)
    except Exception:
        pass

    return blocks


def _extract_pdf(path: Path) -> list[ExtractedBlock]:
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise RuntimeError("PDF extraction requires the pypdfium2 dependency.") from error

    blocks: list[ExtractedBlock] = []
    document = pdfium.PdfDocument(path)
    try:
        for page_number, page in enumerate(document, start=1):
            text_page = page.get_textpage()
            try:
                text = text_page.get_text_range().strip()
            finally:
                text_page.close()

            extraction_type = "digital"
            warnings: list[str] = []

            if not _has_sufficient_text(text):
                try:
                    image = page.render(scale=2).to_pil()
                    text = _ocr_image(image)
                    extraction_type = "ocr"
                except Exception as ocr_error:
                    # Сбой Chandra на этой странице не блокирует обработку других страниц.
                    extraction_type = "ocr"
                    warnings.append(f"OCR failed on page {page_number}: {ocr_error}")

            if text or warnings:
                blocks.append(
                    ExtractedBlock(
                        text=text,
                        source_type="pdf",
                        extraction_type=extraction_type,
                        page_number=page_number,
                        heading=None,  # У PDF плоская структура, заголовки сделает SA-03/SA-01
                        marker=None,
                        warnings=warnings,
                    )
                )
            page.close()
    finally:
        document.close()

    return blocks


def _extract_docx(path: Path) -> list[ExtractedBlock]:
    """Extract paragraphs and tables from DOCX locally with structural awareness."""
    try:
        import docx
    except ImportError as error:
        raise RuntimeError("DOCX extraction requires the python-docx dependency.") from error

    blocks: list[ExtractedBlock] = []

    try:
        document = docx.Document(path)
    except Exception as e:
        # Если файл поврежден, отдаем блок с варнингом, не ломая весь процесс
        return [
            ExtractedBlock(
                text="",
                source_type="docx",
                extraction_type="digital",
                warnings=[f"Failed to open DOCX file: {e}"],
            )
        ]

    current_heading: str | None = None

    # 1. Парсим абзацы текста и отслеживаем заголовки
    for idx, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue

        # Проверяем, является ли абзац заголовком (эвристика по стилям Word)
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name.startswith("Heading"):
            current_heading = text
            # Сам заголовок тоже добавляем как отдельный блок
            blocks.append(
                ExtractedBlock(
                    text=text,
                    source_type="docx",
                    extraction_type="digital",
                    page_number=None,
                    heading=current_heading,
                    marker=f"heading_{idx}",
                )
            )
            continue

        # Обычный абзац текста
        blocks.append(
            ExtractedBlock(
                text=text,
                source_type="docx",
                extraction_type="digital",
                page_number=None,
                heading=current_heading,  # Привязываем последний заголовок
                marker=f"paragraph_{idx}",
            )
        )

    # 2. Парсим таблицы
    for t_idx, table in enumerate(document.tables):
        table_rows: list[str] = []
        for row in table.rows:
            # Собираем непустые ячейки строки через разделитель
            cells_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells_text:
                table_rows.append(" | ".join(cells_text))

        if table_rows:
            table_content = "\n".join(table_rows)
            blocks.append(
                ExtractedBlock(
                    text=table_content,
                    source_type="docx",
                    extraction_type="digital",
                    page_number=None,
                    heading=current_heading,  # Таблица тоже относится к текущему разделу
                    marker=f"table_{t_idx}",
                )
            )

    return blocks


def _extract_image(path: Path) -> list[ExtractedBlock]:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Image OCR requires the optional 'ocr' dependencies.") from error

    try:
        with Image.open(path) as image:
            text = _ocr_image(image.convert("RGB"))
            return [ExtractedBlock(text=text, source_type="image", extraction_type="ocr")]
    except Exception as e:
        return [
            ExtractedBlock(
                text="", source_type="image", extraction_type="ocr", warnings=[str(e)]
            )
        ]


def _has_sufficient_text(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= 32


def _ocr_image(image: Any) -> str:
    global _manager
    # A packaged app must never fetch multi-gigabyte OCR weights as a side
    # effect of searching a folder. Locally cached weights remain usable.
    if getattr(sys, "frozen", False):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if model_is_installed():
        os.environ["MODEL_CHECKPOINT"] = str(model_directory())
    try:
        from chandra.model import BatchInputItem, InferenceManager
    except ImportError as error:
        raise RuntimeError(
            "OCR is unavailable in this app build. Reinstall Study Agent."
        ) from error
    if _manager is None:
        try:
            _manager = InferenceManager(method="hf")
        except (OSError, RuntimeError) as error:
            raise RuntimeError(
                "OCR model is unavailable locally. Open Components & Diagnostics in Settings."
            ) from error
    result = _manager.generate([BatchInputItem(image=image, prompt_type="ocr_layout")])[0]
    if result.error:
        raise RuntimeError("Chandra could not extract text from this page.")
    return result.markdown.strip()


def _cache_path(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        base /= "Study Agent/OCR"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/Study Agent/OCR"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "study-agent/ocr"

    # Безопасное изолированное расширение для новой структуры данных
    return base / f"{digest}.json"
