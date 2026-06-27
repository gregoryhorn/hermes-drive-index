# Real-world metrics

Hermes Drive Index is validated against a live local Google Drive index, but public evidence must stay aggregate-only. This page is safe to publish because it intentionally excludes document names, Drive paths, Drive IDs, snippets, emails, people names, addresses, policy numbers, and raw eval cases.

## What is measured

The local collector (`scripts/collect_real_world_metrics.py`) records:

- package version and git commit
- configured local SQLite index DB size
- aggregate status counts (`indexed`, `indexed_ocr`, `indexed_metadata`, `skipped`, `failed`)
- last index run metadata: mode, timestamps, files scanned/indexed/skipped/failed, bytes downloaded, chunks, and status
- latency for a fixed set of safe generic search terms, published only as aggregate latency/result-count statistics
- aggregate eval scores when the local eval harness output exists: Recall@1, Recall@5, MRR, and average/median latency
- local tool availability for OCR helpers (`ocrmypdf`, `tesseract`) and Python version

## What is intentionally not published

Public docs and README updates must not include:

- personal filenames or folder paths
- Google Drive file/folder IDs
- search snippets or indexed document chunks
- raw search results or top result names
- raw eval query text, expected paths, or per-case result lists
- emails, people names, addresses, policy numbers, account numbers, or other personal identifiers

The private JSONL file stays local under `~/.hermes/drive_index/metrics/` and is not committed.

## Latest sanitized aggregate snapshot

Collected from a live local Drive Index on 2026-06-27 UTC after the targeted metadata-only reindex pass.

| Metric | Value |
| --- | ---: |
| Package version | 0.1.0 |
| Git commit at collection time | `7ec8727` |
| SQLite DB size | 7,122,944 bytes |
| Indexed native/full-text files | 94 |
| Indexed OCR files | 48 |
| Metadata-only indexed files | 5 |
| Skipped files | 471 |
| Failed files | 0 |
| Last run mode | `reindex_metadata_only` |
| Last run status | `success` |
| Last run files scanned | 618 |
| Last run files indexed | 10 |
| Last run bytes downloaded | 8,118,783 |
| Fixed generic search query count | 5 |
| Average generic search latency | 3.264 ms |
| Median generic search latency | 2.99 ms |
| Max generic search latency | 5.59 ms |
| Eval query count | 5 |
| Eval Recall@1 | 1.00 |
| Eval Recall@5 | 1.00 |
| Eval MRR | 1.00 |
| Eval average latency | 41.212 ms |
| OCRmyPDF available | yes |
| Tesseract available | yes |

## Reproduce locally

From the repository root:

```bash
python scripts/collect_real_world_metrics.py --dry-run
python scripts/collect_real_world_metrics.py
```

Outputs:

- private local JSONL: `~/.hermes/drive_index/metrics/hermes-drive-index-metrics.jsonl`
- latest sanitized public summary: `~/.hermes/drive_index/metrics/latest-public-summary.json`

The dry-run prints the public summary without writing. The normal run appends one private aggregate row and rewrites the latest public summary.

## How to interpret this evidence

- The latest metadata-only reindex run scanned 618 Drive entries, reindexed 10 metadata-only rows, converted 5 of them to OCR-indexed rows, and reported 0 failures.
- The local SQLite search path responds in low milliseconds for fixed generic terms. This validates the local-search performance goal without publishing any result documents.
- Recall@1 and Recall@5 are currently 1.00 on the small private local eval set. This supports using the index for assisted retrieval, but it is not yet a broad benchmark.
- OCR support is available on this machine and 48 files are currently represented as OCR-indexed documents.

## Current limitations and evidence gaps

- The eval set is small and private. Public claims should describe it as a small local validation set, not as a general benchmark.
- Public docs intentionally do not publish per-query examples, so readers cannot independently inspect private-result relevance.
- The package install-mode probe can report unavailable metadata in some editable/local environments; this does not affect index metrics.
- Search-quality work should expand aggregate eval reporting while preserving the same privacy boundary.
