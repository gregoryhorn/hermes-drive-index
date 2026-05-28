# Phase E: Proper Package / Plugin Architecture

## Goal

Harden `hermes-drive-index` into a clean, public-repo-safe Python package with a
thin, isolated Hermes plugin adapter, stable import paths, explicit configuration
precedence, and a documented validation + rollback story. Phase E establishes
architecture boundaries and packaging guarantees so that later work (notably OCR)
can slot in without touching the public API, the Hermes adapter, or the on-disk
index schema.

Phase E is **architecture and hardening only**. OCR implementation is explicitly
out of scope (see [Out of Scope](#out-of-scope)); this plan only reserves a clean
slot for it.

## Architecture summary

Target layering (current code already approximates this — Phase E formalizes and
locks it down):

```
hermes_drive_index/
  __init__.py          # version + re-exported public API
  api.py               # public façade: build_index/incremental_update/search/status
  config.py            # config loading + precedence (CLI/env/file/defaults)
  cli.py               # console-script surface (hermes-drive-index ...)
  core/                # pure indexing logic, no Hermes imports
    crawler.py         # Drive crawl + download/export
    extract.py         # text extraction + chunking  (OCR slot lives here)
    index.py           # SQLite schema + write ops
    manifest.py        # incremental planning (pure, network-free)
    models.py          # DriveFile + mime constants + is_indexable
    orchestrator.py    # build/update/search/status orchestration
    search.py          # FTS query + status
    utils.py
  drive/               # auth/client seams (Protocol-based, mockable)
    auth.py            # CredentialProvider protocol
    client.py          # (placeholder) mockable Drive wrapper
  hermes_adapter/      # thin, stateless Hermes integration ONLY
    __init__.py        # register(ctx) entry point
    tools.py           # JSON-safe wrappers + tool schemas
```

**Dependency rule (the core invariant):** `core/` and `api.py` MUST NOT import
anything from `hermes_adapter/`, and MUST NOT import Hermes-only modules
(`hermes_constants`, `model_tools`, `toolsets`, `tools.registry`). The only
Hermes touch-point in the import graph today is the *soft* `hermes_constants`
import in `config.py:10-14`, which already degrades gracefully to
`~/.hermes`. Phase E makes this rule explicit and test-enforced.

## Current repo evidence (file paths)

- Package metadata / entry points: `pyproject.toml`
  - console script: `hermes-drive-index = "hermes_drive_index.cli:main"` (`pyproject.toml:43-44`)
  - plugin entry point: `[project.entry-points."hermes_agent.plugins"] drive_index = "hermes_drive_index.hermes_adapter"` (`pyproject.toml:46-47`)
  - runtime deps: `pypdf>=4`, `python-docx>=1` (`pyproject.toml:34-37`)
  - extras: `test`, `dev` (`pyproject.toml:39-41`)
  - src layout: `where = ["src"]` (`pyproject.toml:49-50`)
- Public API façade: `src/hermes_drive_index/api.py` (wraps `core/orchestrator.py` with `default_config()`)
- Version source of truth: `src/hermes_drive_index/__init__.py:5` (`__version__ = "0.1.0"`) — duplicated in `pyproject.toml:7`
- Config + precedence: `src/hermes_drive_index/config.py`
  - env vars: `HERMES_DRIVE_INDEX_CONFIG`, `_BASE_DIR`, `_ROOT_FOLDER_ID`, `_ROOT_FOLDER_NAME`, `_GOOGLE_API_DIR`, `_DB_PATH`
  - precedence today: **env → local TOML → default** (`config.py:46-56`); no CLI override path
  - soft Hermes dep: `config.py:10-14`
- CLI: `src/hermes_drive_index/cli.py` (subcommands `build`, `update`, `incremental`, `status`, `doctor`, `search`)
- Hermes adapter: `src/hermes_drive_index/hermes_adapter/__init__.py` (`register(ctx)`) and `hermes_adapter/tools.py` (handlers + schemas + `register_tools`)
- Drive seam placeholders: `src/hermes_drive_index/drive/auth.py` (`CredentialProvider` Protocol), `drive/client.py` (empty placeholder)
- SQLite schema: `src/hermes_drive_index/core/index.py:16-65` (`files`, `chunks`, `chunks_fts` FTS5, `runs`); no schema version table
- Tests: `tests/unit/test_adapter.py`, `test_incremental_plan.py`, `test_search_dedup.py`, `test_public_data_guard.py`
- CI: `.github/workflows/ci.yml` (3.11, `pip install -e '.[test]'`, `pytest`)
- Docs: `docs/architecture.md`, `docs/migration.md`, `docs/security.md`, `README.md`, `examples/config.example.toml`
- Privacy hygiene: `.gitignore` (excludes `*.db`, `config.toml`, `*manifest*.json`, tokens, `PHASE_*_REPORT.md`); guard test `tests/unit/test_public_data_guard.py`
- **Stray artifact present:** `.local-test/index.copy.db` exists on disk. It is under a `SKIP_DIRS` entry (`.local-test`) in the guard test (`test_public_data_guard.py:11`) and matched by `.gitignore` `*.db`, so it is not committed — but its presence should be confirmed untracked (see Risks).

### Verified facts (commands run)

- `python -m pytest -q` → `7 passed`.
- `python -c "import hermes_drive_index; print(hermes_drive_index.__version__)"` → `0.1.0`.

## Risks / gaps

1. **Version duplication.** `__init__.py:5` and `pyproject.toml:7` both hardcode `0.1.0`; they can drift. No single source of truth.
2. **No CLI→config override.** `cli.py` calls zero-arg `api.py` functions; config can only be steered by env/TOML. The documented precedence ("explicit API arguments, environment variables, and a local TOML" — `README.md:76`) overstates the current CLI surface, which has no `--root-folder-id`/`--config`/`--db-path` flags.
3. **No index schema version.** `core/index.py` has no `schema_version`/`meta` table. Future migrations (incl. OCR status columns) have no detection hook; `init_db` only ever runs on a fresh `index.new.db`.
4. **Adapter `check_fn` is a no-op.** `check_drive_index_requirements` (`tools.py:17-23`) always returns `True`, even on failure. Acceptable (handlers return structured errors) but undocumented as intentional.
5. **Duplicated registration logic.** `hermes_adapter/__init__.py:register` and `tools.py:register_tools` register the same three tools with near-identical lambdas; `register_tools` adds `max_result_size_chars=20000` only on update. Two code paths can drift.
6. **`build` CLI semantics are surprising.** `cli.py:32-35`: `build --mode incremental*` actually calls `incremental_update()`; only `weekly_full`/`full` call `build_index()`. Documented mode names don't map 1:1 to behavior.
7. **Hard Hermes coupling in crawler.** `core/crawler.py:13-17` does `sys.path.insert` + `import google_api` from `cfg.google_api_dir`. This is a hidden runtime dependency on the Hermes Google Workspace helper, untested and unmockable in CI. The `drive/` seam exists but is unused.
8. **No build/install verification in CI.** CI runs tests but never builds a wheel/sdist or verifies entry points resolve from an installed package.
9. **Terminology drift / public-repo polish.** Earlier package prose used the wrong validation terminology. Per project preference, use "real-world validation" / "Gregory local environment". README/docs/test prose should not ship the old wording.
10. **No OCR config slot.** `DriveIndexConfig` (`config.py:17-26`) has no OCR fields; `extract.py` has no extraction-backend seam. OCR can't be configured today without an API change — Phase E should add the (disabled-by-default) config surface so OCR work later is purely additive.
11. **No env-var precedence test.** Config precedence is untested; regressions would be silent.

## Phased tasks

Each task lists exact files, the change, verification, and the evidence to record.
Tasks are ordered so each is independently shippable. Decision gates (**GATE**)
mark points where a human/Hermes should confirm before proceeding.

### E-1 — Lock the core/adapter dependency boundary (test-enforced)

- **Files:** add `tests/unit/test_import_boundaries.py`.
- **Change:** add a test that imports `hermes_drive_index.core.*` and `hermes_drive_index.api` and asserts that `sys.modules` after import contains no `hermes_adapter` submodule, and that `core` source files contain no `from ..hermes_adapter`/`import hermes_adapter` references (static scan via `pathlib` + regex, mirroring `test_public_data_guard.py` style). Also assert `core/` does not import `model_tools`/`toolsets`.
- **Verify:** `python -m pytest tests/unit/test_import_boundaries.py -q` passes.
- **Evidence:** test output; list of core files scanned.

### E-2 — Single-source the version

- **Files:** `pyproject.toml`, `src/hermes_drive_index/__init__.py`.
- **Change:** use dynamic version: set `[project] dynamic = ["version"]` and
  `[tool.setuptools.dynamic] version = {attr = "hermes_drive_index.__version__"}`.
  Remove the hardcoded `version = "0.1.0"` from `[project]`. Keep `__version__` in `__init__.py` as the source of truth.
- **Verify:**
  - `python -m pip install -e . && python -c "import importlib.metadata as m; print(m.version('hermes-drive-index'))"` → `0.1.0`.
  - `python -m pytest -q` still passes.
- **Evidence:** both version strings match from a clean install.

### E-3 — Add config precedence + CLI overrides (no behavior change to defaults)

- **Files:** `src/hermes_drive_index/config.py`, `src/hermes_drive_index/api.py`, `src/hermes_drive_index/cli.py`, new `tests/unit/test_config_precedence.py`.
- **Change:**
  - Add a `load_config(overrides: dict | None = None)` (or extend `default_config`) so explicit kwargs win over env, which win over TOML, which win over defaults — making `README.md:76` true. Keep `default_config()` behavior identical when no overrides are passed.
  - Thread an optional `cfg`/overrides through `api.py` functions (default `None` → `default_config()`), preserving the current zero-arg signatures for the adapter.
  - Add global CLI flags: `--config PATH`, `--root-folder-id`, `--db-path`, `--base-dir` (all optional; default to current behavior when omitted).
- **Verify:**
  - New test sets a TOML file + env var + explicit override and asserts the resolved field follows precedence (explicit > env > TOML > default).
  - `hermes-drive-index status` with no flags still resolves the same paths as before.
- **Evidence:** precedence test output; `status` JSON before/after identical with no flags.
- **GATE:** confirm CLI flag names with Hermes before finalizing (affects cron wrappers).

### E-4 — Reserve OCR config slot (disabled by default; no OCR logic)

- **Files:** `src/hermes_drive_index/config.py`, `examples/config.example.toml`, `docs/architecture.md`.
- **Change:** add OCR-related fields to `DriveIndexConfig` with **safe defaults**:
  - `ocr_enabled: bool = False`
  - `ocr_image_enabled: bool = False`
  - `include_folders: tuple[str, ...] = ()` (empty = all under root)
  - `exclude_folders: tuple[str, ...] = ()` (e.g. local config can later add `Photos/`)
  - Load these from env (`HERMES_DRIVE_INDEX_OCR`, `..._OCR_IMAGE`, `..._INCLUDE_FOLDERS`, `..._EXCLUDE_FOLDERS`) and TOML, defaulting off.
  - Document (commented-out) keys in `examples/config.example.toml`.
  - **Do not** wire these into `extract.py`/`orchestrator.py` yet beyond reading them; OCR remains entirely unimplemented.
- **Verify:** `python -c "from hermes_drive_index.config import default_config as d; c=d(); print(c.ocr_enabled, c.ocr_image_enabled, c.exclude_folders)"` → `False False ()` with no local overrides.
- **Evidence:** default values printed; example config diff shows only commented OCR keys.
- **Rationale:** This is the "clean slot" for OCR. Defaults stay off so the public package never OCRs arbitrary photos. Gregory's local config can opt in *after* OCR is built.

### E-5 — Add index schema version / meta table + migration hook

- **Files:** `src/hermes_drive_index/core/index.py`, `src/hermes_drive_index/core/orchestrator.py`, new `tests/unit/test_schema_version.py`.
- **Change:**
  - Add a `meta(key text primary key, value text)` table in `init_db` and write `schema_version = "1"` on creation.
  - Add a `read_schema_version(con)` helper and a no-op-when-current `migrate(con)` stub that raises a clear error on unknown future versions. Do **not** alter existing `files`/`chunks`/`chunks_fts`/`runs` shapes (preserves on-disk compatibility — existing DBs simply report `schema_version = None`, treated as "1/legacy").
  - This reserves a migration path for OCR status columns later without forcing a rebuild now.
- **Verify:** new test creates a DB, asserts `read_schema_version` returns `"1"`; opening a DB without the `meta` table returns the legacy sentinel without error.
- **Evidence:** test output; confirm a pre-existing index (copy of `.local-test/index.copy.db`) still opens and `status` works.

### E-6 — De-duplicate Hermes tool registration

- **Files:** `src/hermes_drive_index/hermes_adapter/__init__.py`, `src/hermes_drive_index/hermes_adapter/tools.py`.
- **Change:** define a single `TOOL_SPECS` list (name, toolset, schema, handler, check_fn, emoji, optional `max_result_size_chars`) in `tools.py`. Have both `register(ctx)` and `register_tools(registry)` iterate it, so the two entry points cannot drift. Keep tool **names and schemas byte-stable** (`drive_index_search/_status/_update`).
- **Verify:** `test_adapter.py` still passes; add an assertion that the set of registered tool names from a fake `ctx`/`registry` is exactly `{drive_index_search, drive_index_status, drive_index_update}` and schemas are unchanged.
- **Evidence:** test output; diff shows single source list.

### E-7 — Document adapter contract + JSON-safety guarantees

- **Files:** `docs/architecture.md`, docstrings in `hermes_adapter/tools.py`.
- **Change:** document that (a) handlers always return a JSON string with a top-level `success` bool and `package_version`; (b) `check_fn` intentionally returns `True` so tools stay discoverable and surface structured errors at call time; (c) `top_k` is clamped 1–25; (d) `update` is long-running and cron-wrapper compatible via the CLI. No code change beyond docstrings unless a JSON-safety hole is found.
- **Verify:** add a test asserting every handler's output round-trips through `json.loads` for the error path and a mocked success path (extend `test_adapter.py`).
- **Evidence:** test output.

### E-8 — CLI smoke + `doctor`/`status` JSON-shape tests

- **Files:** new `tests/unit/test_cli_smoke.py`.
- **Change:** invoke `cli.main(["--version"])`, `cli.main(["doctor"])`, `cli.main(["status"])` with a temp `HERMES_DRIVE_INDEX_DB_PATH` pointing at a non-existent DB; assert exit code 0 and that `status` reports `{"exists": false}`. Use `capsys` to parse stdout JSON. Mock `build_drive_service` is not needed since these paths don't crawl.
- **Verify:** `python -m pytest tests/unit/test_cli_smoke.py -q` passes offline.
- **Evidence:** test output.

### E-9 — Packaging build + entry-point resolution verification

- **Files:** `.github/workflows/ci.yml` (add a job/step), optional `docs/architecture.md` note.
- **Change:** add a CI step that builds and verifies discovery:
  ```bash
  python -m pip install build
  python -m build            # wheel + sdist into dist/
  python -m pip install dist/*.whl
  hermes-drive-index --version
  python -c "import importlib.metadata as m; \
    eps=[e for e in m.entry_points(group='hermes_agent.plugins') if e.name=='drive_index']; \
    assert eps, 'plugin entry point missing'; print(eps[0].load())"
  ```
  Run in a fresh venv so it validates a **regular (non-editable) install**, complementing the existing editable test job.
- **Verify:** CI job green; console script + plugin entry point resolve from the wheel.
- **Evidence:** CI log showing wheel built, `--version` output, entry point loaded.
- **GATE:** confirm whether to publish artifacts or keep build-only (no PyPI in Phase E).

### E-10 — Public-repo hygiene pass

- **Files:** `README.md`, `docs/*`, `.gitignore`, confirm working tree.
- **Change:**
  - Replace old validation wording in `README.md:49` (and any roadmap copy) with "real-world validation" / "Gregory local environment" wording. Public prose and test names should use the preferred terminology.
  - Confirm `.local-test/` is git-ignored and untracked: run `git status --porcelain --ignored | rg local-test`.
  - Re-affirm `docs/security.md` no-commit list still matches reality after E-4/E-5 (no new private fields written to committed files).
- **Verify:** `python -m pytest tests/unit/test_public_data_guard.py -q` passes; `git status` clean of private artifacts; repository prose uses the preferred validation wording.
- **Evidence:** grep output; `git status --ignored` excerpt.

### E-11 — Refresh architecture/migration docs to match shipped state

- **Files:** `docs/architecture.md`, `docs/migration.md`.
- **Change:** update `docs/architecture.md` (currently a 11-line stub) to describe the locked boundaries, config precedence, schema-version/meta table, OCR slot, and adapter contract delivered by E-1…E-9. Note in `docs/migration.md` that the package CLI/plugin path is primary and the legacy `site-packages` wrapper is rollback-only.
- **Verify:** docs reference only files/flags that exist (cross-check against `cli.py`, `config.py`).
- **Evidence:** doc diff; manual cross-check list.

## Verification matrix

| Concern | Command | Expected | Task |
| --- | --- | --- | --- |
| Unit suite | `python -m pytest -q` | all pass (currently 7) | all |
| Core/adapter boundary | `pytest tests/unit/test_import_boundaries.py` | no Hermes/adapter imports in core | E-1 |
| Version single-source | `pip install -e . && python -c "import importlib.metadata as m;print(m.version('hermes-drive-index'))"` | `0.1.0` | E-2 |
| Config precedence | `pytest tests/unit/test_config_precedence.py` | explicit>env>TOML>default | E-3 |
| OCR defaults off | `python -c "from hermes_drive_index.config import default_config as d;print(d().ocr_enabled)"` | `False` | E-4 |
| Schema version | `pytest tests/unit/test_schema_version.py` | `"1"`; legacy opens cleanly | E-5 |
| Tool names stable | `pytest tests/unit/test_adapter.py` | 3 tools, unchanged schemas | E-6 |
| Adapter JSON-safe | `pytest tests/unit/test_adapter.py` (extended) | all outputs `json.loads`-able | E-7 |
| CLI smoke (offline) | `pytest tests/unit/test_cli_smoke.py` | exit 0; `{"exists": false}` | E-8 |
| Build + entry points | `python -m build && pip install dist/*.whl && hermes-drive-index --version` | wheel builds; EP loads | E-9 |
| No private data | `pytest tests/unit/test_public_data_guard.py`; `git status --ignored` | pass; no private artifacts | E-10 |
| Plugin discovery (Hermes env, manual) | `python` snippet from `docs/migration.md:79-87` | `drive_index_search/_status/_update` | E-9/E-11 |

### Real-world validation (Gregory local environment)

Run against the live `Personal Files` index **without exposing private contents**.
These produce only aggregate counts/paths — never document text:

```bash
# Health + plugin discovery
hermes-drive-index doctor

# Index status: counts, db size, last run (no snippets)
hermes-drive-index status

# No-op incremental: should show scanned>0, unchanged>0, indexed/reindexed low, failed=0
hermes-drive-index update --mode incremental_manifest
hermes-drive-index status
```

For search validation, use `--top 1` and **do not paste snippet text into the
repo, PRs, or logs**; report only latency, result count, and whether the expected
file path appeared. Treat `~/.hermes/drive_index/personal_files/index.db` as
sensitive (per `docs/security.md`).

## Rollback notes

- **No schema break.** E-5 only *adds* a `meta` table; existing `files`/`chunks`/`chunks_fts`/`runs` are untouched, and existing `index.db` files keep working (treated as legacy/v1). No forced rebuild.
- **Config back-compat.** E-3/E-4 add optional fields/flags with defaults equal to current behavior; `default_config()` with no env/TOML resolves the same paths as today. Existing `~/.hermes/drive_index/config.toml` keeps working unchanged.
- **Adapter back-compat.** Tool names and schemas stay byte-stable (E-6), so Hermes sessions/cron wrappers need no changes. Hermes caches schemas per session — restart the gateway after upgrading.
- **Legacy wrapper guardrail.** The legacy direct `site-packages` wrapper remains **rollback-only**. Migration order from `docs/migration.md`: keep the old wrapper until one package-CLI cron run succeeds, then disable static wiring. To roll back: disable `drive_index` in `plugins.enabled`, restore the prior wrapper, point cron at the old path, re-run `hermes-drive-index doctor`.
- **Version dynamic-version rollback (E-2):** if dynamic versioning misbehaves on the target build backend, revert to a static `version =` in `pyproject.toml` and keep `__version__` in sync manually.

## Out of scope

- **OCR implementation itself** — scanned/image-only PDFs, image OCR
  (JPEG/PNG/TIFF/WebP, optional HEIC), OCR metrics (`indexed_ocr`,
  `indexed_ocr_image`, `files_ocred`, `images_ocred`), and OCR-specific include/
  exclude enforcement are **not** built in Phase E. Phase E only reserves the
  config slot (E-4), schema-migration hook (E-5), and extraction-backend boundary
  so OCR is additive later. OCR stays opt-in/local-first and off by default.
- Replacing the `core/crawler.py` `import google_api` coupling with a fully
  mocked `drive/client.py` Drive wrapper. Risk #7 is documented; building the fake
  Drive client + synthetic fixtures (README roadmap) is a follow-on phase.
- PyPI publishing / release automation (E-9 is build + discovery verification only).
- Expanded evaluation metrics (Recall@k, MRR) — README roadmap, separate work.

## Open questions

1. **CLI flag names (E-3):** confirm `--config`/`--root-folder-id`/`--db-path`/`--base-dir` spellings so cron wrappers can adopt them once.
2. **`build --mode` semantics (Risk #6):** keep the current surprising mapping for back-compat, or make `build` always full and `update` always incremental? Recommend documenting current behavior in E-11 and deferring a breaking change.
3. **Dynamic version backend (E-2):** confirm `setuptools` dynamic attr works in the target CI/build environment, else keep static version.
4. **Build artifacts (E-9):** build-only in CI, or upload wheel/sdist as workflow artifacts for manual install testing?
