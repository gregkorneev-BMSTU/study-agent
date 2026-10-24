"""Download and locate the optional local Chandra OCR model."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

MODEL_ID = "datalab-to/chandra-ocr-2"
MODEL_REVISION = "af93b47dba1b47b6640c86ccf487ed2260ab9a09"


def model_directory() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "Study Agent/Models/Chandra"


def model_is_installed() -> bool:
    directory = model_directory()
    marker = directory / ".study-agent-model.json"
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(metadata, dict)
        and metadata.get("repo_id") == MODEL_ID
        and metadata.get("revision") == MODEL_REVISION
        and (directory / "config.json").is_file()
        and (directory / "model.safetensors").is_file()
    )


def download_model(progress: Callable[[dict[str, Any]], None] | None = None) -> Path:
    if model_is_installed():
        return model_directory()

    try:
        from huggingface_hub import HfApi, hf_hub_download
        from tqdm.auto import tqdm
    except ImportError as error:
        raise RuntimeError("Chandra download requires the optional OCR dependencies.") from error

    directory = model_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = directory / ".study-agent-model.json"
    marker.unlink(missing_ok=True)
    progress_lock = threading.Lock()

    class ProgressBar(tqdm):
        def update(self, n: int = 1) -> bool | None:
            updated = super().update(n)
            if progress and self.total and n:
                with progress_lock:
                    progress(
                        {
                            "current": self.n,
                            "total": self.total,
                        }
                    )
            return updated

    try:
        siblings = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION).siblings
        for sibling in siblings:
            hf_hub_download(
                repo_id=MODEL_ID,
                filename=sibling.rfilename,
                revision=MODEL_REVISION,
                local_dir=str(directory),
                tqdm_class=ProgressBar,
            )
    except Exception as error:
        raise RuntimeError(f"Chandra model download failed: {error}") from error
    if not (directory / "config.json").is_file() or not (directory / "model.safetensors").is_file():
        raise RuntimeError("The downloaded Chandra model is incomplete. Retry the download.")

    temporary_marker = marker.with_suffix(".tmp")
    temporary_marker.write_text(
        json.dumps({"repo_id": MODEL_ID, "revision": MODEL_REVISION}), encoding="utf-8"
    )
    temporary_marker.replace(marker)
    return directory
