# R&D backlog

Canonical tracking now lives on the Hermes Kanban board `hermes-drive-index`. This Markdown file is a publishable mirror/summary only; use Kanban task status for active routing and handoff state.

Current Kanban cards:

- `t_060f9919` — Build privacy-preserving OCR parameter benchmark
- `t_575b5760` — Expand aggregate retrieval eval set
- `t_13e5f3ff` — Investigate ranking improvements for metadata-heavy results
- `t_c90de7e9` — Reduce metadata-only indexed files
- `t_7e63ecc7` — Evaluate layout/table extraction pipeline

Backlog items are candidates until a research report provides enough evidence to justify an implementation plan. Implemented items remain listed here as a publishable summary, while Kanban remains the source of truth for active routing and handoff state.

## Template

```markdown
### Title

- Source report/date:
- Hypothesis:
- Expected user/project benefit:
- Required real-world evidence:
- Implementation risk:
- Privacy risk:
- Proposed test/eval:
- Status: candidate | ready-for-plan | blocked | rejected | implemented
```

## Current candidates

### Expand aggregate retrieval eval set

- Source report/date: initial monitoring setup, 2026-06-26
- Hypothesis: a larger private eval set with only aggregate public reporting will make search-quality changes safer to evaluate.
- Expected user/project benefit: fewer ranking regressions and stronger public evidence without leaking personal document details.
- Required real-world evidence: 15-25 private eval cases, aggregate Recall@1/Recall@5/MRR/latency only, and a privacy guard that blocks raw case publication.
- Implementation risk: medium; eval harness and reporting paths need careful separation between private cases and public summaries.
- Privacy risk: medium; raw eval queries and expected paths are private and must remain local-only.
- Proposed test/eval: private eval run must emit aggregate-only public JSON and pass repository public-data guard tests.
- Status: candidate

### Investigate ranking improvements for metadata-heavy results

- Source report/date: initial monitoring setup, 2026-06-26
- Hypothesis: BM25 tuning, chunk grouping, and metadata/body weighting can improve Recall@1 while preserving Recall@5.
- Expected user/project benefit: faster first-result retrieval for Hermes document lookups.
- Required real-world evidence: before/after aggregate Recall@1, Recall@5, MRR, and latency on the private eval set.
- Implementation risk: medium; FTS query/ranking changes can regress some document classes.
- Privacy risk: low if only aggregate metrics are published; medium if debugging output leaks result names/snippets.
- Proposed test/eval: run unit tests plus private eval before and after any ranking experiment; fail if Recall@5 or latency regresses materially.
- Status: candidate

### Reduce metadata-only indexed files

- Source report/date: initial monitoring setup, 2026-06-26
- Hypothesis: targeted OCR/extraction improvements can convert some metadata-only rows into full-text or OCR-indexed rows.
- Expected user/project benefit: better search coverage for scanned or awkward PDFs.
- Required real-world evidence: metadata-only count decreases, failed count remains zero, and aggregate eval does not regress.
- Implementation risk: medium; OCR and layout tools can be slow or brittle.
- Privacy risk: medium; extraction debugging can expose text if logs are not sanitized.
- Proposed test/eval: targeted local run with aggregate status counts before/after and no private text in logs/docs.
- Status: implemented — 2026-06-27 aggregate validation reduced metadata-only rows from 10 to 5 with 0 failed files and no aggregate eval regression.

### Build privacy-preserving OCR parameter benchmark

- Source report/date: OCR/extraction R&D, 2026-06-27
- Hypothesis: OCRmyPDF preprocessing and Tesseract profile options can convert some current metadata-only documents into indexable OCR text without broad indexing changes.
- Expected user/project benefit: fewer metadata-only rows and better retrieval coverage for scanned PDFs/images.
- Required real-world evidence: aggregate before/after status counts for metadata-only candidates, per-mode runtime, `files_failed=0`, and no regression in private aggregate Recall@5/MRR.
- Implementation risk: medium; OCR options such as rotation, deskew, background removal, language selection, PSM, and DPI can help some scans while hurting others or increasing runtime.
- Privacy risk: medium; OCR output and debug logs may expose private text unless the benchmark emits only aggregate metrics.
- Proposed test/eval: read-only benchmark over metadata-only candidates with aggregate-only output: conversions to `indexed_ocr`/`indexed`, failures, runtime, bytes downloaded, and private eval deltas.
- Status: implemented — read-only aggregate OCR parameter benchmark was used to justify the metadata-only reduction pass.

### Evaluate layout/table extraction pipeline

- Source report/date: OCR/extraction R&D, 2026-06-27
- Hypothesis: layout-aware extraction tools can improve reading order and table text coverage for documents where raw OCR/native text is insufficient for retrieval.
- Expected user/project benefit: better search snippets and retrieval for invoices, statements, receipts, and form-like PDFs.
- Required real-world evidence: sanitized fixture results plus private aggregate eval improvements, dependency/runtime profile, and clear fallback behavior when tools fail.
- Implementation risk: medium-high; Docling/Camelot/pdfplumber-style tooling adds dependencies and may perform inconsistently across native, scanned, ruled-table, and borderless-table PDFs.
- Privacy risk: medium; table and layout debugging can leak structured private content if fixtures/logs are not sanitized.
- Proposed test/eval: bakeoff native extraction vs pdfplumber/Camelot/Docling on synthetic fixtures first, then private aggregate-only measurement of Recall@1/MRR, metadata-only count, extraction duration, and failure rate.
- Status: candidate
