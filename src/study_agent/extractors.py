"""Local text extraction with lazy Chandra OCR for scans and images."""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from study_agent.ocr_model import model_directory, model_is_installed

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
OCR_SUFFIXES = {".pdf", *IMAGE_SUFFIXES}
_manager: Any | None = None


def extract_document(path: Path) -> str:
    """Extract document text; use local Chandra only when a page needs OCR."""
    if path.suffix.lower() not in OCR_SUFFIXES:
        return path.read_text(encoding="utf-8")

    cache_path = _cache_path(path)
    if cache_path.is_file():
        return cache_path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".pdf":
        text = _extract_pdf(path)
    else:
        text = _extract_image(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = cache_path.with_name(f"{cache_path.stem}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(cache_path)
    return text


def _extract_pdf(path: Path) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise RuntimeError("PDF extraction requires the pypdfium2 dependency.") from error

    pages: list[str] = []
    document = pdfium.PdfDocument(path)
    try:
        for page_number, page in enumerate(document, start=1):
            text_page = page.get_textpage()
            try:
                text = text_page.get_text_range().strip()
            finally:
                text_page.close()
            if not _has_sufficient_text(text):
                image = page.render(scale=2).to_pil()
                text = _ocr_image(image)
            if text:
                pages.append(f"## Page {page_number}\n\n{text}")
            page.close()
    finally:
        document.close()
    return "\n\n".join(pages)


def _extract_image(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Image OCR requires the optional 'ocr' dependencies.") from error
    with Image.open(path) as image:
        return _ocr_image(image.convert("RGB"))


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
    return base / f"{digest}.md"
