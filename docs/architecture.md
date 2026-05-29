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

## Google Drive API calls, retries, and rate limits

Drive access is concentrated in `core/crawler.py`. `build_drive_service()` imports
Gregory's existing Google Workspace helper from the configured `google_api_dir`
and calls `google_api.build_service("drive", "v3")` (`core/crawler.py:13-17`).
That helper builds a `googleapiclient.discovery.build(...)` service with stored
OAuth credentials and refreshes expired tokens before service creation
(`~/.hermes/skills/productivity/google-workspace/scripts/google_api.py:177-202`).

The package itself does not wrap Google Drive calls with custom retry, backoff,
throttling, or 429/5xx handling. Folder listing is a straightforward paginated
`service.files().list(..., pageSize=1000, supportsAllDrives=True,
includeItemsFromAllDrives=True).execute()` loop (`core/crawler.py:20-54`), and
file retrieval is a single `req.execute()` per file (`core/crawler.py:70-83`).
Google-native Docs/Slides are exported as `text/plain`, Google Sheets as
`text/csv`, and all other supported files use `files().get_media(...)`
(`core/crawler.py:70-79`). There is no `MediaIoBaseDownload` chunking, no
explicit `num_retries`, no sleep/backoff loop, and no package-level byte-size
limit before download.

Failure handling is at the indexing orchestration boundary. In a full build,
each indexable file is wrapped in `try/except`; failures increment
`files_failed`, append `{file_id, path, mime_type, error}` to `metrics["errors"]`,
and store the file row with status `failed` (`core/orchestrator.py:59-72`).
Incremental updates use the same per-reindex handling inside a single DB
transaction and roll back only for failures outside the per-file catch block
(`core/orchestrator.py:128-157`). Successful build metrics are persisted to
`last_build_metrics.json` (`core/orchestrator.py:83-86,160-164`). Operationally,
this means rate-limit or transient download errors are recorded as file failures;
they are not automatically retried by hermes-drive-index.

## Text extraction and OCR pipeline

Indexability is MIME-driven in `core/models.py`. Default indexable types are PDF,
plain/markdown/CSV text, JSON, `.docx`, legacy `.doc`, Google Docs, Google
Sheets, and Google Slides; arbitrary `text/*` also indexes. Folders and videos
are skipped. Images are skipped by default, and become indexable only when image
OCR is enabled and the MIME type is one of PNG, JPEG, TIFF, BMP, or WebP
(`core/models.py:7-48`).

`core/index.py:index_file()` deletes any previous rows for the file, downloads or
exports it, counts downloaded bytes from the local cache file size, calls
`extract_text()`, chunks extracted text with `chunk_text()`, and writes both
`chunks` and `chunks_fts` rows (`core/index.py:137-187`). Empty extraction is not
a hard failure: the file is stored as `indexed_metadata`, the searchable chunk is
`name + path + mime_type`, and the `files_metadata_only` metric is incremented
(`core/index.py:159-170`). Native text extraction statuses are `indexed` for
normal extraction and `indexed_ocr` when OCR produced text (`core/index.py:171-177`).
Chunks default to 2400 characters with 250-character overlap for overlong
paragraphs (`core/extract.py:66-88`).

Extraction backends are intentionally simple and local (`core/extract.py:18-63`):

* PDFs use `pypdf.PdfReader(...).pages[i].extract_text()`; page-level extraction
  exceptions are embedded in the extracted text as `[page N extraction error: ...]`
  rather than aborting the whole PDF (`core/extract.py:18-30`).
* `.docx` uses `python-docx` paragraph text (`core/extract.py:33-37`).
* Google Docs/Slides/Sheets have already been exported to `.txt`/`.csv`, and
  Google-native files, `text/*`, and JSON are read with `Path.read_text(errors="replace")`
  (`core/crawler.py:70-76`, `core/extract.py:61-62`).
* Legacy `application/msword` is recognized as indexable but currently returns
  empty text, so it falls back to metadata-only indexing (`core/extract.py:57-60`).
* Unsupported MIME types return empty text and are either skipped before download
  or become metadata-only if they reached extraction (`core/models.py:41-48`,
  `core/extract.py:63`).

OCR is opt-in, not automatic. `ocr_enabled` controls scanned-PDF fallback and
`ocr_image_enabled` controls image OCR; both default false in config and can be
set by explicit CLI/API overrides, `HERMES_DRIVE_INDEX_OCR`,
`HERMES_DRIVE_INDEX_OCR_IMAGE`, or TOML (`config.py:37-40,85-129`; `cli.py:33-35`).
For PDFs, native `pypdf` extraction runs first; `ocr_pdf()` is called only if the
PDF produced no text and PDF OCR is enabled (`core/extract.py:44-50`). For
images, extraction returns empty unless image OCR is enabled, then calls
`ocr_image()` (`core/extract.py:51-56`). The README recommends scoping Drive
folders before enabling image OCR, but `include_folders` and `exclude_folders`
are currently configuration fields only; no source path applies those filters in
crawl or indexing (`config.py:40-41,114-128`).

OCR wrappers live in `core/ocr.py` and deliberately use external commands rather
than hard runtime dependencies. PDF OCR requires `ocrmypdf`; image OCR requires
`tesseract` (`core/ocr.py:16-22`). `ocr_pdf()` runs
`ocrmypdf --skip-text --quiet input.pdf output.pdf` with a 120-second timeout,
then extracts text from the OCR'd PDF with the same `extract_pdf()` path
(`core/ocr.py:25-42`). `ocr_image()` runs
`tesseract <image> stdout --quiet` with a 120-second timeout (`core/ocr.py:47-60`).
Missing commands, timeouts, command failures, and empty OCR output return `None`
instead of raising (`core/ocr.py:25-62`). `index_file()` records unavailable OCR
as `ocr_skipped_unavailable` and metadata-only error text, records OCR failures
as `ocr_failed`, and otherwise falls back to metadata-only indexing when OCR is
requested but yields no chunks (`core/index.py:142-170`). OCR language is not
configured in the command line; Tesseract/ocrmypdf defaults apply.

## Drive listing and pagination

Drive crawling is implemented in `core/crawler.py:crawl(service, root_id, root_name)` and is invoked for both full builds by `core/orchestrator.py:build_index()` and manifest incremental updates by `core/orchestrator.py:incremental_update()`.

The crawler uses `service.files().list(...).execute()` only; there is no `changes().list` implementation or Drive changes-token resume path in the current code. For each folder, the exact list parameters in `core/crawler.py:crawl` are:

* `q="'<folder_id>' in parents and trashed=false"`, so every request lists one folder's direct, non-trashed children.
* `spaces="drive"`.
* `fields="nextPageToken, files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,parents)"`, which is the partial response mask. The code reads `id`, `name`, `mimeType`, `size`, `modifiedTime`, `md5Checksum`, and `webViewLink`; `parents` is requested but is not currently stored on `core/models.py:DriveFile`.
* `pageSize=1000`.
* `pageToken=page`, where `page` starts as `None` for each folder and is then replaced with `resp.get("nextPageToken")` after every page.
* `supportsAllDrives=True` and `includeItemsFromAllDrives=True`.

No `orderBy` parameter is supplied, so result ordering is the Drive API default. The crawl walks folders with an in-memory LIFO `stack`: it starts with `(root_id, root_name)`, appends folder children to the stack when `DriveFile.mime_type == GOOGLE_FOLDER`, and emits paths as `"<parent path>/<name>"` in `core/crawler.py:crawl`.

Loop termination is per-folder: after processing `resp.get("files", [])`, the crawler sets `page = resp.get("nextPageToken")` and breaks the inner pagination loop when no token is returned. It then continues with the next folder on the stack until the stack is empty. There is no persisted page token, start page token, or checkpoint for resuming a partially completed crawl; `core/orchestrator.py:build_index()` and `core/orchestrator.py:incremental_update()` both begin by calling `crawl(...)` from the configured root and must complete the crawl before indexing/planning proceeds. Incremental behavior is manifest-diff based after the fresh crawl: `core/orchestrator.py:incremental_update()` passes the crawled `DriveFile` list and `core/index.py:existing_files(...)` into `core/manifest.py:plan_incremental_actions(...)`, which decides `reindex`, `metadata_only`, `unchanged`, `skip`, and `delete` actions.

## Shortcut handling

There is no explicit Google Drive shortcut resolution in the current source tree. A source search finds no references to `application/vnd.google-apps.shortcut`, `shortcutDetails`, `targetId`, or shortcut-specific traversal/download logic. The crawler only requests `id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,parents` from Drive (`core/crawler.py:27-35`) and stores those fields in `DriveFile` (`core/crawler.py:38-47`; `core/models.py:29-39`), so it does not request the shortcut target metadata needed to resolve a shortcut.

Because the shortcut MIME type is not present in `INDEXABLE_MIMES` and is not equal to `GOOGLE_FOLDER`, `is_indexable()` returns false for shortcuts (`core/models.py:15-26,41-48`). Full builds record such files with status `skipped` via `insert_skipped_file()` (`core/orchestrator.py:59-63`; `core/index.py:102-106`); incremental builds similarly plan them into `skip` if the skipped row is new or changed (`core/manifest.py:23-30`) and then write the skipped row (`core/orchestrator.py:133-135`). A shortcut to a folder is not traversed as the target folder, because only items whose own MIME type is `application/vnd.google-apps.folder` are pushed onto the crawler stack (`core/crawler.py:48-50`).

## Shared-drive / team-drive handling

The crawler opts into shared-drive-aware listing on every folder listing call with `supportsAllDrives=True` and `includeItemsFromAllDrives=True` (`core/crawler.py:27-35`). Non-Google-native file downloads also pass `supportsAllDrives=True` to `files().get_media(...)` (`core/crawler.py:77-79`).

The current source tree does not set `corpora`, `driveId`, `teamDriveId`, `includeTeamDriveItems`, or any equivalent shared-drive selector. In practice, the indexer crawls downward from the configured `root_folder_id` only (`core/orchestrator.py:25-37,90-100`; `core/crawler.py:20-54`). Shared-drive items can be indexed when the configured root or its descendants are accessible to the authenticated Drive account and returned by that parent query, but the package does not enumerate all shared drives and does not target a specific shared drive by id. Google Workspace exports use `files().export_media(fileId=..., mimeType=...)` without an explicit `supportsAllDrives` option in this code path (`core/crawler.py:70-76`).

## Index schema version

`core/index.py` defines `SCHEMA_VERSION` and writes it into a `meta(key, value)`
table on DB creation. `read_schema_version(con)` returns the stored version, or
`None` for legacy DBs built before the `meta` table existed (treated as v1).
`migrate(con)` is a no-op for current/legacy versions and raises on an unknown
future version. Existing `files`/`chunks`/`chunks_fts`/`runs` shapes are
unchanged, so existing indexes keep working without a forced rebuild.

## Deleted, trashed, renamed, and moved files

The verified incremental update path is a manifest-diff crawl, not the Google
Drive Changes API. `core/orchestrator.py::incremental_update` calls
`core/crawler.py::crawl`, reads all existing rows with
`core/index.py::existing_files`, plans actions with
`core/manifest.py::plan_incremental_actions`, then applies the resulting
`delete`, `skip`, `metadata_only`, and `reindex` lists in one SQLite transaction.

`core/crawler.py::crawl` recursively lists each folder with the query
`'<folder_id>' in parents and trashed=false` and requests
`id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,parents`. The
crawler constructs the indexed path from the current parent traversal and file
name. Because trashed files are excluded from the crawl, the index treats a
trashed file the same way as a deleted or moved-out-of-scope file during an
incremental update.

Verified behavior from the source:

* Deleted, trashed, or moved out of the indexed tree: if a previously indexed
  `file_id` is absent from the latest crawl, `plan_incremental_actions` adds it
  to `plan["delete"]` (`core/manifest.py`). `incremental_update` applies that by
  calling `delete_file_from_index` (`core/orchestrator.py`), which removes rows
  from `chunks_fts`, `chunks`, and `files` (`core/index.py`). The code does not
  keep tombstone rows.
* Renamed or moved within the indexed tree without content changes: Drive keeps
  the same `file_id`, so the file is still present in the latest crawl. If
  `file_changed` is false but `name`, `path`, or `web_view_link` differs,
  `plan_incremental_actions` adds it to `plan["metadata_only"]`
  (`core/manifest.py`). `incremental_update` calls `update_file_metadata`, which
  updates the `files` row and, when `name` or `path` changed, reinserts that
  file's FTS rows with the new metadata (`core/index.py`). This avoids a
  download/export and text re-extraction for pure rename/path changes.
* Modified content: `file_changed` compares Google Docs/Sheets/Slides by
  `modified_time`, binary files by `md5_checksum` when available, and otherwise
  by `modified_time` or `size_bytes` (`core/manifest.py`). Changed files go to
  `plan["reindex"]`; `index_file` first deletes the old rows for that `file_id`,
  then downloads/exports and extracts the current file (`core/index.py`).
* Full rebuild: `build_index` writes a fresh `index.new.db` from the current
  crawl and atomically replaces the prior DB with it (`core/orchestrator.py`).
  It therefore has no separate deletion/tombstone cleanup routine; rows for
  absent files disappear because the new database is built only from crawled
  files.

The unit regression `tests/unit/test_incremental_plan.py` covers the pure
planning logic for unchanged, renamed/moved-within-tree, changed, new, skipped,
and deleted file IDs. Behavior for a true Drive delete and a Drive trash action
is inferred from the crawler's `trashed=false` query plus the absent-`file_id`
delete plan; there is no separate source path that calls Drive's Changes API or
records delete/trash tombstones.

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
