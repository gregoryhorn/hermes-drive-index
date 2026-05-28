# Architecture

`hermes-drive-index` is a small Python package with a thin, isolated Hermes
plugin adapter. The layering is locked down so later work (notably OCR) can slot
in without touching the public API, the adapter, or the on-disk index schema.

## Layering

```
hermes_drive_index/
  __init__.py          # version (single source of truth) + public API re-exports
  api.py               # public façade: build_index/incremental_update/search/status
  config.py            # config loading + precedence
  cli.py               # console script (hermes-drive-index ...)
  core/                # pure indexing logic, no Hermes imports
    crawler.py         # Drive crawl + download/export
    extract.py         # text extraction + chunking (OCR slot lives here)
    index.py           # SQLite schema + write ops + schema version
    manifest.py        # incremental planning (pure, network-free)
    models.py          # DriveFile + mime constants + is_indexable
    orchestrator.py    # build/update/search/status orchestration
    search.py          # FTS query + status
    utils.py
  drive/               # auth/client seams (Protocol-based, mockable)
  hermes_adapter/      # thin, stateless Hermes integration ONLY
```

**Dependency rule (core invariant):** `core/` and `api.py` MUST NOT import the
`hermes_adapter/` package or Hermes-only modules (`hermes_constants`,
`model_tools`, `toolsets`, `tools.registry`). The only Hermes touch-point is the
*soft* `hermes_constants` import in `config.py`, which degrades gracefully to
`~/.hermes`. This boundary is enforced by `tests/unit/test_import_boundaries.py`.

## Configuration precedence

`config.load_config(overrides)` resolves each field with the precedence:

1. **Explicit overrides** (CLI flags / API arguments)
2. **Environment variables** (`HERMES_DRIVE_INDEX_*`)
3. **Local TOML config file**
4. **Built-in defaults**

`default_config()` is `load_config()` with no overrides and resolves the same
paths as before. CLI global flags `--config`, `--root-folder-id`, `--db-path`,
and `--base-dir` map to overrides; omitting them preserves prior behavior.

## OCR slot (reserved, disabled by default)

`DriveIndexConfig` carries `ocr_enabled`, `ocr_image_enabled`, `include_folders`,
and `exclude_folders`, all defaulting off/empty. They are read from env/TOML but
**not yet wired into extraction or orchestration** — OCR is unimplemented. The
defaults ensure the public package never OCRs arbitrary content; a local config
can opt in once OCR is built. The extraction backend boundary lives in
`core/extract.py`.

## Index schema version

`core/index.py` defines `SCHEMA_VERSION` and writes it into a `meta(key, value)`
table on DB creation. `read_schema_version(con)` returns the stored version, or
`None` for legacy DBs built before the `meta` table existed (treated as v1).
`migrate(con)` is a no-op for current/legacy versions and raises on an unknown
future version. Existing `files`/`chunks`/`chunks_fts`/`runs` shapes are
unchanged, so existing indexes keep working without a forced rebuild.

## Hermes adapter contract

Tool definitions live in a single `tools.TOOL_SPECS` list; both `register(ctx)`
and `register_tools(registry)` iterate it, so the two entry points cannot drift.
Tool names and schemas (`drive_index_search`/`_status`/`_update`) are
byte-stable. Each handler:

* returns a JSON **string** with top-level `success` (bool) and `package_version`
  on both success and error paths (errors never propagate as exceptions);
* `check_fn` intentionally returns `True` so tools stay discoverable and surface
  structured errors at call time;
* `drive_index_search` clamps `top_k` to 1–25;
* `drive_index_update` is long-running and shares the CLI code path, so it is
  cron-wrapper compatible.

## Packaging

The version is single-sourced from `hermes_drive_index.__version__` via
setuptools dynamic metadata. CI builds a wheel/sdist and verifies the console
script and `hermes_agent.plugins` entry point resolve from a non-editable
install.
