"""Configuration for hermes-drive-index.

Configuration precedence (highest to lowest):

1. Explicit overrides passed to :func:`load_config` (e.g. CLI flags / API args)
2. Environment variables (``HERMES_DRIVE_INDEX_*``)
3. A local TOML config file
4. Built-in defaults

``default_config()`` is preserved as a zero-argument convenience that resolves
the same paths as before when no overrides are supplied.
"""

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
    # OCR is disabled by default and consumed only when explicitly enabled.
    ocr_enabled: bool = False
    ocr_image_enabled: bool = False
    include_folders: tuple[str, ...] = ()
    exclude_folders: tuple[str, ...] = ()


def _local_config_path(hermes_home: Path, override: str | None = None) -> Path:
    raw = override or os.getenv("HERMES_DRIVE_INDEX_CONFIG") or hermes_home / "drive_index" / "config.toml"
    return Path(raw).expanduser()


def _load_local_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _path(value, default: Path) -> Path:
    return Path(value if value is not None else default).expanduser()


def _pick(override, env_name: str, local: dict, key: str):
    """Resolve a single value: explicit override > env > TOML > None."""
    if override is not None:
        return override
    env_val = os.getenv(env_name)
    if env_val is not None:
        return env_val
    return local.get(key)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if str(v).strip())
    return tuple(item for item in str(value).split(os.pathsep) if item.strip())


def load_config(overrides: dict | None = None) -> DriveIndexConfig:
    """Resolve configuration following explicit > env > TOML > default precedence.

    ``overrides`` keys map to ``DriveIndexConfig`` fields (``config_path``,
    ``base_dir``, ``root_folder_id``, ``root_folder_name``, ``google_api_dir``,
    ``db_path``, ``ocr_enabled``, ``ocr_image_enabled``, ``include_folders``,
    ``exclude_folders``). ``None`` values are ignored (treated as "not set").
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    hermes_home = Path(get_hermes_home())
    config_path = _local_config_path(hermes_home, overrides.get("config_path"))
    local = _load_local_config(config_path)

    base_dir = _path(
        _pick(overrides.get("base_dir"), "HERMES_DRIVE_INDEX_BASE_DIR", local, "base_dir"),
        hermes_home / "drive_index" / "personal_files",
    )
    root_folder_id = _pick(overrides.get("root_folder_id"), "HERMES_DRIVE_INDEX_ROOT_FOLDER_ID", local, "root_folder_id")
    root_folder_name = _pick(overrides.get("root_folder_name"), "HERMES_DRIVE_INDEX_ROOT_FOLDER_NAME", local, "root_folder_name") or "Personal Files"
    google_api_dir = _path(
        _pick(overrides.get("google_api_dir"), "HERMES_DRIVE_INDEX_GOOGLE_API_DIR", local, "google_api_dir"),
        hermes_home / "skills" / "productivity" / "google-workspace" / "scripts",
    )
    db_path = _path(
        _pick(overrides.get("db_path"), "HERMES_DRIVE_INDEX_DB_PATH", local, "db_path"),
        base_dir / "index.db",
    )
    ocr_enabled = _as_bool(_pick(overrides.get("ocr_enabled"), "HERMES_DRIVE_INDEX_OCR", local, "ocr_enabled"))
    ocr_image_enabled = _as_bool(_pick(overrides.get("ocr_image_enabled"), "HERMES_DRIVE_INDEX_OCR_IMAGE", local, "ocr_image_enabled"))
    include_folders = _as_tuple(_pick(overrides.get("include_folders"), "HERMES_DRIVE_INDEX_INCLUDE_FOLDERS", local, "include_folders"))
    exclude_folders = _as_tuple(_pick(overrides.get("exclude_folders"), "HERMES_DRIVE_INDEX_EXCLUDE_FOLDERS", local, "exclude_folders"))

    return DriveIndexConfig(
        root_folder_id=root_folder_id,
        root_folder_name=root_folder_name,
        base_dir=base_dir,
        cache_dir=base_dir / "cache",
        db_path=db_path,
        google_api_dir=google_api_dir,
        config_path=config_path,
        ocr_enabled=ocr_enabled,
        ocr_image_enabled=ocr_image_enabled,
        include_folders=include_folders,
        exclude_folders=exclude_folders,
    )


def default_config() -> DriveIndexConfig:
    return load_config()
