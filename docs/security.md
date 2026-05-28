# Security and privacy

The local SQLite FTS index can contain full text from private Google Drive documents. Treat it as sensitive data.

Never commit:

- index databases
- OAuth tokens or client secrets
- real folder IDs
- real manifests
- real golden queries
- private crawl logs or reports

Default logs and status output should prefer aggregate counts and paths, not document snippets. Debug output may include sensitive content and should be handled accordingly.
