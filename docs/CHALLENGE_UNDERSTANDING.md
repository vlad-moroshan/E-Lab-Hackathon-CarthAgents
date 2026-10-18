# Project guide

> Implementation status and measured results: see [IMPLEMENTATION.md](IMPLEMENTATION.md).

Build an unattended agent with one command that accepts a folder of unfamiliar German fixed-asset documents and produces, for each document, **a filled Arbeitsversion workbook and a JSON file with one record per value**. Each JSON record carries row identity, field, amount, source pointer and uncertainty/problem flags. Keep the extraction JSON as the source for workbook conversion so both outputs describe the same evidence.

The [challenge materials](../challenge/) contain the briefs and workbook template. Detailed inventories and mappings live in the [reference](REFERENCE.md); unresolved contract and evaluation issues live in [open questions](OPEN_QUESTIONS.md).

## Requirements

- Code retrieves and parses every financial amount from source cells, positioned PDF text or OCR tokens. Layout interpretation must not invent amounts.
- Model OCR is allowed; retain its text and coordinates and parse the numeric tokens in code. The scope of acceptable generative vision transcription remains unspecified.
- Every extracted amount needs evidence: PDF page and bounding box, or workbook sheet and cell. Preserve raw text and sign/unit conversion alongside normalized values internally.
- Report printed values, including broken totals, and flag inconsistencies. Arithmetic is a check, not permission to repair the client document.
- Abstain explicitly when uncertain. An empty amount cell in an identified source amount column counts as zero; a missing column, unreadable crop or inapplicable field does not. The extraction schema records explicit reasons for abstention.
- Preserve actual granularity, years, leaf rows, printed subtotals/totals and carry-overs. Summary rows cannot reveal individual assets. Repeated summaries must not be counted twice.
- Keep answer keys, generator internals, profiles and filename-based layout shortcuts out of runtime extraction. They are development/evaluation aids.

The brief scores a correct value with valid evidence **+1**, a flagged blank **0**, and a wrong value or unsupported pointer **−3**. Arithmetic agreement helps diagnose errors but does not prove correctness or completeness: missing zero rows, duplicates and compensating mistakes can still reconcile.

## JSON contract

Runtime output follows [extraction.schema.json](../carth/extraction.schema.json). Each document contains source identity/fingerprint, source rows, per-value records and document flags. A value record has row ID, field, integer cents or null, source pointer, flags, raw parsing/unit/sign trace and its workbook destination. Every blank carries a reason. Unknown source metadata is omitted; generator seed, family and invented-name assertions are not required.

[corpus.schema.json](../carth/eval/corpus.schema.json) and `validate-corpus` retain the original answer-key contract. They do not validate the runtime extraction envelope. The local evaluator accepts both runtime value records and fixture-style rows with per-value `pointers`.

JSON and XLSX outputs use the same collision-safe document ID. For unique stems it is the stem; collisions gain a hash of the relative path, including extension. Source paths, content hashes and frame versions validate ingestion caches.

## Reporting years

JSON output is **per document, not limited to one year**. `meta.years` lists the reporting years and each row carries its own `year`. Preserve all years represented in the source.

**10 of the 72 supplied documents contain two full annual schedules:**

| Documents | Reporting years | Rows per year |
| --- | --- | ---: |
| `f01_net_spiegel_08` | 2024 and 2025 | 33 |
| `f07_sap_class_summary_05` | 2024 and 2025 | 20 |
| `f08_excel_spiegel_2y_01`, `_02`, `_04`–`_08` | 2024 and 2025 | 10 |
| `f08_excel_spiegel_2y_03` | 2023 and 2024 | 10 |

The Arbeitsversion's core sheets represent **one reporting year with prior-year comparison values**: each grid has one fiscal-end input, and the register has no reporting-year column. A prior-year book-value column is not a second full annual movement schedule. The writer creates separate annual copies of the relevant sheets inside one document workbook. It labels the reporting year and leaves an unknown fiscal end date blank; JSON retains every year. This is the local export convention, pending organiser confirmation.

## Proposed pipeline and workbook output

The extraction pipeline combines implemented evidence/writer stages with pending automatic layout discovery:

1. Ingest native workbook cells or positioned PDF/OCR tokens, retaining coordinates, types, formulas, cached values, display formats and visibility information.
2. Identify relevant pages/tables, reporting periods and units. Interpret column meanings, block structure, row roles and hierarchy from the document itself.
3. Parse source tokens into integer cents in code, preserving the raw signed reading and explicit normalization. Use geometry as well as numeric syntax when separating glued amounts.
4. Check applicable row laws, printed subtotals, year continuity, source pointers and coverage of rows/columns. Re-read ambiguous regions; keep source inconsistencies distinct from uncertain extraction.
5. Serialize and validate the JSON output. Use the extraction schema, including explicit abstention reasons.
6. Convert the saved JSON into a copy of [Arbeitsversion-merged-layout-20.xlsx](../challenge/Arbeitsversion-merged-layout-20.xlsx). Conversion consumes the extraction result rather than re-extracting the documents. Put actual assets in `Anlagenverzeichnis` and appropriate summaries in `Gitter nach Anlagenklasse` / `Gitter nach Bilanzposition`, following the [field mapping](REFERENCE.md#core-amount-mapping-corpus-fields-to-actual-workbook-columns). Convert cents to numeric EUR. Preserve printed totals and distinguish derived workbook cells. Keep reporting years separate as described above.

Start with f00, then native Excel and text PDFs, block/summary layouts, and OCR/orientation handling. Evaluate held-out families and layout mutations; their performance is evidence about generalization, not knowledge of the hidden test. Avoid implementing the template's full audit workflow before the batch extraction path works.

## Current implementation and checks

### Installation

The core package installs with `uv sync --locked`. CPU OCR uses the `ocr` extra, which declares NumPy, PaddleOCR and the PaddlePaddle CPU runtime. A fresh locked install and one-page PP-OCRv6-small inference were verified on macOS Apple Silicon with Python 3.12.13, alongside the regression suite and corpus validation. The core package's broader Python requirement does not establish OCR wheel availability on every Python version/platform.

To keep the OCR environment separate from an existing project environment:

```sh
UV_PROJECT_ENVIRONMENT=out/ocrenv uv sync --locked --python 3.12 --extra ocr
out/ocrenv/bin/carth ocr A3-Hackathon-Corpus --device cpu --model small --workers 1 --out out/tokens_paddle_small
```

The first OCR run needs access to download model weights; subsequent runs can use cached weights. No GPU or CUDA runtime is required. Increase worker count only after measuring the available RAM budget.

Alternate engines remain experimental and are installed separately. Add `--extra doctr` or `--extra tesseract` to the sync command **alongside `--extra ocr`**: both engines currently use Paddle's shared orientation classifier. Tesseract additionally requires an installed Tesseract executable and German (`deu`) language data; `pytesseract` is only the Python wrapper. Neither alternate engine is part of the verified Paddle smoke test.

The lockfile pins transitive dependencies; use `--locked` to prevent resolution changes during setup. See the [PaddleOCR installation documentation](https://www.paddleocr.ai/main/en/version3.x/installation.html) for inference-engine requirements and [uv environment configuration](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path) for `UV_PROJECT_ENVIRONMENT`.

### Commands and implementation status

The authoritative setup is [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock) and [carth/](../carth/). Ingest and OCR discover source files without keys. OCR selects pages with no text or substantial image content even when headings are selectable. Original page boxes remain reversible; native text and OCR evidence are retained separately. OCR defaults to one worker; explicit parallelism needs a measured memory budget. No fresh OCR benchmark was run for these fixes.

`carth run INPUT OUT --specs LAYOUTS` writes both required outputs using reviewed source references. It does not yet discover layouts automatically. Missing specs yield flagged outputs and a nonzero exit. Layout specs and limitations are documented in [IMPLEMENTATION.md](IMPLEMENTATION.md). Corpus generators have separate dependencies and can delete outputs; preserve the supplied corpus.

Run these existing checks from the repository root:

```sh
uv run carth validate-corpus
uv run python -m unittest discover -s tests -v
```

To inspect the evidence layer for native Excel and text PDFs:

```sh
uv run carth ingest --types xlsx,pdf
uv run carth recall --formats xlsx,pdf
```

After predictions exist:

```sh
uv run carth check --pred out/pred
uv run carth eval --pred out/pred -v
```

| Command | What it establishes | Limits |
| --- | --- | --- |
| `ingest` | Positioned PDF/Excel tokens, formula/cache state and source fingerprint. | No semantic layout discovery; batch failures are recorded and fail the command. |
| `ocr` | Original-page OCR boxes plus reading frames and orientation diagnostics. | Optional OCR environment; no deskew or independent pixel validation. One worker by default. |
| `run` | Per-value JSON and copied Arbeitsversion from fingerprinted layout references. | Automatic layout/spec generation is unfinished. Null values and missing specs are explicit and return nonzero. |
| `recall` | Diagnostic source-token coverage against keys, including missing caches in the denominator. | No semantic extraction or visual proof; missing caches fail unless `--partial`. |
| `validate-corpus` | Original answer-key schema/cross-field checks. | Does not validate runtime outputs or financial correctness. |
| `check` | Supplied integrity checks plus complete-batch presence checks. | No truth/completeness score. Missing outputs fail unless `--partial`; scanner checks cannot validate pixels. |
| `eval` | Local +1/0/−3 heuristic reference benchmark with signed net fields, identity and observed Excel conflicts. | Learned columns and OCR references are not independent truth. Weak/multi references earn no credit. |
| `oracle` | Key or conservative reference-generated predictions for evaluator diagnostics. | Not extraction, an official score or a mathematical ceiling. |

The [reference](REFERENCE.md) holds the corpus inventory, domain distinctions, paired-document relationships, workbook catalogs and sample index. [Open questions](OPEN_QUESTIONS.md) is the single review list for unresolved inconsistencies.
