"""Config precedence: explicit > env > TOML > default (Phase E-3/E-4)."""

from __future__ import annotations

from hermes_drive_index.config import default_config, load_config


def _write_toml(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_toml_over_default(tmp_path):
    cfg_path = _write_toml(tmp_path, 'root_folder_id = "from-toml"\n')
    cfg = load_config({"config_path": str(cfg_path)})
    assert cfg.root_folder_id == "from-toml"


def test_env_over_toml(tmp_path, monkeypatch):
    cfg_path = _write_toml(tmp_path, 'root_folder_id = "from-toml"\n')
    monkeypatch.setenv("HERMES_DRIVE_INDEX_ROOT_FOLDER_ID", "from-env")
    cfg = load_config({"config_path": str(cfg_path)})
    assert cfg.root_folder_id == "from-env"


def test_explicit_over_env_and_toml(tmp_path, monkeypatch):
    cfg_path = _write_toml(tmp_path, 'root_folder_id = "from-toml"\n')
    monkeypatch.setenv("HERMES_DRIVE_INDEX_ROOT_FOLDER_ID", "from-env")
    cfg = load_config({"config_path": str(cfg_path), "root_folder_id": "from-explicit"})
    assert cfg.root_folder_id == "from-explicit"


def test_default_config_equivalent_to_load_config_no_overrides():
    assert default_config() == load_config()


def test_ocr_defaults_off(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_DRIVE_INDEX_OCR", raising=False)
    monkeypatch.delenv("HERMES_DRIVE_INDEX_OCR_IMAGE", raising=False)
    monkeypatch.delenv("HERMES_DRIVE_INDEX_INCLUDE_FOLDERS", raising=False)
    monkeypatch.delenv("HERMES_DRIVE_INDEX_EXCLUDE_FOLDERS", raising=False)
    cfg = load_config({"config_path": str(tmp_path / "missing.toml")})
    assert cfg.ocr_enabled is False
    assert cfg.ocr_image_enabled is False
    assert cfg.include_folders == ()
    assert cfg.exclude_folders == ()


def test_ocr_env_toggles(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_DRIVE_INDEX_OCR", "true")
    monkeypatch.setenv("HERMES_DRIVE_INDEX_EXCLUDE_FOLDERS", "Photos")
    cfg = load_config({"config_path": str(tmp_path / "missing.toml")})
    assert cfg.ocr_enabled is True
    assert cfg.exclude_folders == ("Photos",)


def test_ocr_pdf_args_accept_only_safe_preprocessing_args(tmp_path):
    cfg = load_config({"config_path": str(tmp_path / "missing.toml"), "ocr_pdf_args": ["--rotate-pages", "--deskew", "--image-dpi", "300"]})

    assert cfg.ocr_pdf_args == ("--rotate-pages", "--deskew", "--image-dpi", "300")


def test_ocr_pdf_args_reject_sidecar_output(tmp_path):
    try:
        load_config({"config_path": str(tmp_path / "missing.toml"), "ocr_pdf_args": ["--sidecar", "/tmp/private.txt"]})
    except ValueError as e:
        assert "Unsupported OCRmyPDF argument" in str(e)
    else:  # pragma: no cover - explicit assertion for readability
        raise AssertionError("unsafe OCRmyPDF argument was accepted")
