import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from study_agent import ocr_model


def test_model_directory_uses_application_data_override(tmp_path: Path, monkeypatch) -> None:
    data_directory = tmp_path / "StudyAgent"
    monkeypatch.setenv("STUDY_AGENT_DATA_DIR", str(data_directory))

    assert ocr_model.model_directory() == data_directory / "Models" / "Chandra"


def test_model_install_downloads_pinned_snapshot_and_reports_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "Chandra"
    monkeypatch.setattr(ocr_model, "model_directory", lambda: directory)
    download_args: list[dict[str, object]] = []

    class API:
        def model_info(self, repo_id: str, revision: str) -> SimpleNamespace:
            assert repo_id == ocr_model.MODEL_ID
            assert revision == ocr_model.MODEL_REVISION
            return SimpleNamespace(
                siblings=[
                    SimpleNamespace(rfilename="config.json"),
                    SimpleNamespace(rfilename="model.safetensors"),
                ]
            )

    def hf_hub_download(**kwargs: object) -> str:
        download_args.append(kwargs)
        progress_type = kwargs["tqdm_class"]
        progress = progress_type(total=100, desc="weights")
        progress.update(25)
        progress.close()
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / str(kwargs["filename"])
        if destination.name == "config.json":
            destination.write_text("{}", encoding="utf-8")
        else:
            destination.write_bytes(b"weights")
        return str(destination)

    hub = ModuleType("huggingface_hub")
    hub.HfApi = API  # type: ignore[attr-defined]
    hub.hf_hub_download = hf_hub_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    events: list[dict[str, object]] = []

    result = ocr_model.download_model(events.append)

    assert result == directory
    assert [call["filename"] for call in download_args] == ["config.json", "model.safetensors"]
    assert all(call["repo_id"] == ocr_model.MODEL_ID for call in download_args)
    assert all(call["revision"] == ocr_model.MODEL_REVISION for call in download_args)
    assert all(call["local_dir"] == str(directory) for call in download_args)
    assert events[0]["current"] == 25
    assert ocr_model.model_is_installed()


def test_model_is_not_installed_without_complete_marker(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "Chandra"
    directory.mkdir()
    (directory / "config.json").touch()
    (directory / "model.safetensors").touch()
    monkeypatch.setattr(ocr_model, "model_directory", lambda: directory)

    assert not ocr_model.model_is_installed()


def test_existing_model_skips_download(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "Chandra"
    directory.mkdir()
    (directory / "config.json").touch()
    (directory / "model.safetensors").touch()
    (directory / ".study-agent-model.json").write_text(
        '{"repo_id":"datalab-to/chandra-ocr-2",'
        '"revision":"af93b47dba1b47b6640c86ccf487ed2260ab9a09"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr_model, "model_directory", lambda: directory)

    assert ocr_model.download_model() == directory
