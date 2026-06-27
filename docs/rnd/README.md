# R&D loop

This directory holds privacy-preserving research reports for Hermes Drive Index. The recurring Hermes jobs are designed to research improvements, cite sources, and propose experiments without touching private Google Drive content or implementing changes directly.

## Streams

- `search-quality/` — SQLite FTS5 ranking, BM25 tuning, hybrid lexical/vector search, reranking, chunk grouping, and document-retrieval evaluation.
- `ocr-extraction/` — OCRmyPDF, Tesseract settings, scanned PDF/image extraction, table/layout extraction, and metadata-only reduction.
- `product-release/` — comparable local document search tools, privacy-first positioning, README evidence expectations, install flows, and public-release polish.

Each report should:

1. cite sources with URLs;
2. separate evidence from recommendations;
3. propose concrete experiments;
4. define the metric/test that would prove the improvement;
5. avoid private filenames, snippets, Drive IDs, and document contents;
6. add candidate backlog items to `docs/rnd/backlog.md` only when there is enough evidence to justify tracking.

## Operating boundaries

- Reports are local docs until Gregory approves publication.
- Jobs must not push to GitHub.
- Jobs must not create new cron jobs.
- Jobs must not mutate Drive files or enable broader auto-organization.
- Implementation work remains a separate, explicitly approved planning/build loop.
