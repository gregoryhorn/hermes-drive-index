"""Configuration for hermes-drive-index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib

try:
    from hermes_constants import get_hermes_home
except Exception:  # pragma: no cover - used outside Hermes
    def get_hermes_home() -> str:
        return str(Path.home() / ".hermes")


@dataclass(frozen=True)
class DriveIndexConfig:
    root_folder_id: str | None
    root_folder_name: str
    base_dir: Path
    cache_dir: Path
    db_path: Path
    google_api_dir: Path
    config_path: Path


def _local_config_path(hermes_home: Path) -> Path:
    return Path(os.getenv("HERMES_DRIVE_INDEX_CONFIG", hermes_home / "drive_index" / "config.toml")).expanduser()


def _load_local_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _path(value, default: Path) -> Path:
    return Path(value if value is not None else default).expanduser()


def default_config() -> DriveIndexConfig:
    hermes_home = Path(get_hermes_home())
    config_path = _local_config_path(hermes_home)
    local = _load_local_config(config_path)
    base_dir = _path(
        os.getenv("HERMES_DRIVE_INDEX_BASE_DIR") or local.get("base_dir"),
        hermes_home / "drive_index" / "personal_files",
    )
    root_folder_id = os.getenv("HERMES_DRIVE_INDEX_ROOT_FOLDER_ID") or local.get("root_folder_id")
    root_folder_name = os.getenv("HERMES_DRIVE_INDEX_ROOT_FOLDER_NAME") or local.get("root_folder_name") or "Personal Files"
    google_api_dir = _path(
        os.getenv("HERMES_DRIVE_INDEX_GOOGLE_API_DIR") or local.get("google_api_dir"),
        hermes_home / "skills" / "productivity" / "google-workspace" / "scripts",
    )
    db_path = _path(os.getenv("HERMES_DRIVE_INDEX_DB_PATH") or local.get("db_path"), base_dir / "index.db")
    return DriveIndexConfig(
        root_folder_id=root_folder_id,
        root_folder_name=root_folder_name,
        base_dir=base_dir,
        cache_dir=base_dir / "cache",
        db_path=db_path,
        google_api_dir=google_api_dir,
        config_path=config_path,
    )
