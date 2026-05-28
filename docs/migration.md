# Migration Guide: From Prototype to Hermes Drive Index Package

This guide explains how to move from a local prototype or direct Hermes `site-packages` tool wrapper to the packaged `hermes-drive-index` CLI and Hermes plugin.

## Target architecture

- Core Google Drive indexing logic lives in the external Python package `hermes-drive-index`.
- Hermes integration is a thin plugin adapter exposed through the `hermes_agent.plugins` entry point group.
- Local/private runtime configuration stays outside the repository.
- The existing SQLite DB schema is preserved so a live index can migrate without a forced full rebuild.

The packaged CLI / plugin path is the **primary** integration. The legacy direct
`site-packages` tool wrapper is **rollback-only**: keep it available until one
package-CLI cron run succeeds, then disable the static wiring.

## 1. Install the package

From the repository root:

```bash
python -m pip install -e '.[test]'
```

For a pipx-installed Hermes Agent:

```bash
pipx inject --editable hermes-agent /path/to/hermes-drive-index
```

## 2. Add local config

Create a local config file outside the repo, for example:

```toml
# ~/.hermes/drive_index/config.toml
root_folder_name = "Personal Files"
root_folder_id = "YOUR_GOOGLE_DRIVE_FOLDER_ID"
base_dir = "/home/you/.hermes/drive_index/personal_files"
db_path = "/home/you/.hermes/drive_index/personal_files/index.db"
```

Never commit this file if it contains real folder IDs or private local paths.

## 3. Enable the Hermes plugin

In `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - drive_index
```

Start a new Hermes session or restart the gateway after changing plugin configuration.

## 4. Verify CLI behavior

```bash
hermes-drive-index doctor
hermes-drive-index status
hermes-drive-index search "example query" --top 3 --json
```

For a no-change incremental update:

```bash
hermes-drive-index update --mode incremental_manifest
```

Expected healthy result for an unchanged index:

- files scanned is nonzero
- files unchanged is nonzero
- files indexed/reindexed is zero or low
- files failed is zero
- DB counts remain stable

## 5. Verify Hermes plugin discovery

From the Hermes Python environment:

```bash
python - <<'PY'
import model_tools
from toolsets import validate_toolset, resolve_toolset
from tools.registry import registry
print(validate_toolset('drive_index'))
print(resolve_toolset('drive_index'))
print(registry.get_tool_names_for_toolset('drive_index'))
PY
```

Expected tools:

- `drive_index_search`
- `drive_index_status`
- `drive_index_update`

## 6. Cut over scheduled updates

Prefer a script-only cron job that calls the package CLI directly:

```bash
hermes-drive-index update --mode incremental_manifest
hermes-drive-index status
```

Keep the old wrapper available until one package-based cron run succeeds. After that, remove or disable direct `site-packages` wrappers and static toolset wiring.

## Rollback

If the package path fails during migration:

1. Disable the plugin in `plugins.enabled`.
2. Restore the previous wrapper or toolset wiring from backup.
3. Point cron back to the old path.
4. Re-run `hermes-drive-index doctor` and inspect Hermes gateway logs before retrying.
