# Architecture

Phase E architecture target:

- `hermes_drive_index.core`: crawler, extractors, SQLite index, search, incremental planning.
- `hermes_drive_index.drive`: mockable Google Drive client and credential provider seams.
- `hermes_drive_index.hermes_adapter`: thin stateless Hermes tool registration.
- `hermes-drive-index` CLI: local status/search/update/doctor commands.

The initial E1 implementation wraps the migrated prototype behind a stable API so DB schema and behavior remain compatible during packaging.
