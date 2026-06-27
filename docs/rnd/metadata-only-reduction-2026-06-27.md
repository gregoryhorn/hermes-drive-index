# Metadata-only reduction run — 2026-06-27

## Scope and privacy boundary

This run used only aggregate local metrics and tool output. The notes below intentionally exclude filenames, Drive paths, Drive IDs, search snippets, raw OCR text, raw eval cases, and document contents.

## Change applied

The production OCR-enabled indexing path now passes the benchmark-supported OCRmyPDF preprocessing arguments `--rotate-pages --deskew` into PDF OCR reindexing. These arguments came from the prior read-only aggregate OCR benchmark, where the `rotate_deskew` mode converted the most metadata-only candidates without increasing failures or reducing aggregate eval quality.

The arguments are configurable through `DriveIndexConfig.ocr_pdf_args`, the `HERMES_DRIVE_INDEX_OCR_PDF_ARGS` environment variable, TOML `ocr_pdf_args`, or repeated CLI `--ocr-pdf-arg` flags. OCR remains opt-in; the default package still does not run OCR unless `--ocr` / config / env enables it.

## Before/after aggregate status counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Indexed native/full-text files | 94 | 94 | 0 |
| Indexed OCR files | 43 | 48 | +5 |
| Metadata-only indexed files | 10 | 5 | -5 |
| Skipped files | 471 | 471 | 0 |
| Failed files | 0 | 0 | 0 |

## Targeted reindex aggregate run

Command:

```bash
hermes-drive-index --ocr update --mode reindex_metadata_only --json
```

Aggregate result:

| Metric | Value |
| --- | ---: |
| Files scanned | 618 |
| Files considered | 10 |
| Files reindexed | 10 |
| Files indexed OCR | 5 |
| Files remaining metadata-only from the pass | 5 |
| Files failed | 0 |
| OCR attempted | 7 |
| OCR failed | 0 |
| OCR unavailable skips | 0 |
| Bytes downloaded | 8,118,783 |
| Chunks written | 20 |
| Duration | 62.84 seconds |

## Aggregate eval check

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Eval queries | 5 | 5 | 0 |
| Recall@1 | 0.80 | 1.00 | +0.20 |
| Recall@5 | 1.00 | 1.00 | 0.00 |
| MRR | 0.90 | 1.00 | +0.10 |
| Average eval latency | 44.851 ms | 41.212 ms | -3.639 ms |

## Verification commands

```bash
python -m pytest tests/unit/test_reindex_metadata_only.py::test_reindex_metadata_only_reindexes_only_metadata_rows -q
python -m pytest tests/unit/test_ocr.py tests/unit/test_reindex_metadata_only.py tests/unit/test_ocr_benchmark.py tests/unit/test_config_precedence.py -q
hermes-drive-index status --json
python ~/.hermes/drive_index/eval_drive_index.py --repeat 1
python scripts/collect_real_world_metrics.py --dry-run
```

## Privacy check

The committed documentation records aggregate metrics only. Private local JSON outputs used during validation were kept under `/tmp` or the local Hermes metrics directory and were not copied into this repository.
