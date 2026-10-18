# Project guide

Build an unattended agent that accepts a folder of unfamiliar German fixed-asset documents and produces **one JSON file per document using the extraction-output schema**. A separate, optional step converts that JSON into the Arbeitsversion workbook. XLSX generation is not a prerequisite for extraction or JSON delivery.

The [challenge materials](../challenge/) contain the briefs and workbook template. Detailed inventories and mappings live in the [reference](REFERENCE.md); unresolved contract and evaluation issues live in [open questions](OPEN_QUESTIONS.md).

## Requirements

- Code retrieves and parses every financial amount from source cells, positioned PDF text or OCR tokens. Layout interpretation must not invent amounts.
- Model OCR is allowed; retain its text and coordinates and parse the numeric tokens in code. The scope of acceptable generative vision transcription remains unspecified.
- Every extracted amount needs evidence: PDF page and bounding box, or workbook sheet and cell. Preserve raw text and sign/unit conversion alongside normalized values internally.
- Report printed values, including broken totals, and flag inconsistencies. Arithmetic is a check, not permission to repair the client document.
- Abstain explicitly when uncertain. An empty amount cell in an identified source amount column counts as zero; a missing column, unreadable crop or inapplicable field does not. Use the [output statuses](OUTPUT_FORMAT.md#rows-and-values) to distinguish these cases.
- Preserve actual granularity, years, leaf rows, printed subtotals/totals and carry-overs. Summary rows cannot reveal individual assets. Repeated summaries must not be counted twice.
- Keep answer keys, generator internals, profiles and filename-based layout shortcuts out of runtime extraction. They are development/evaluation aids.

The brief scores a correct value with valid evidence **+1**, a flagged blank **0**, and a wrong value or unsupported pointer **−3**. Arithmetic agreement helps diagnose errors but does not prove correctness or completeness: missing zero rows, duplicates and compensating mistakes can still reconcile.

## JSON contract

[carth/output/extraction.schema.json](../carth/output/extraction.schema.json) defines extraction output: `schema_version`, source-identifiable `meta`, year-tagged `rows` and detected `findings`. Each financial field contains its amount, observation/abstention status and evidence. Unknown optional metadata is omitted; unreadable values are null with reasons. Generator-only metadata and `planted` are prohibited.

See [Extraction JSON](OUTPUT_FORMAT.md) for the field contract, complete example and validation commands. [carth/eval/corpus.schema.json](../carth/eval/corpus.schema.json) validates supplied ground-truth keys, whose generator metadata and test annotations are not extraction targets.

Output files are `<doc_id>.pred.json` in `out/pred/`; supplied keys are `<doc_id>.key.json` beside their documents. The required official submission filename convention is unspecified.

## Reporting years

JSON output is **per document, not limited to one year**. `meta.years` lists the reporting years and each row carries its own `year`. Preserve all years represented in the source.

**10 of the 72 supplied documents contain two full annual schedules:**

| Documents | Reporting years | Rows per year |
| --- | --- | ---: |
| `f01_net_spiegel_08` | 2024 and 2025 | 33 |
| `f07_sap_class_summary_05` | 2024 and 2025 | 20 |
| `f08_excel_spiegel_2y_01`, `_02`, `_04`–`_08` | 2024 and 2025 | 10 |
| `f08_excel_spiegel_2y_03` | 2023 and 2024 | 10 |

The Arbeitsversion's core sheets represent **one reporting year with prior-year comparison values**: each grid has one fiscal-end input, and the register has no reporting-year column. A prior-year book-value column is not a second full annual movement schedule. An optional converter therefore needs a target year or separate annual workbooks to represent multi-year JSON. The export convention is unspecified; the JSON must retain both years regardless.

## Proposed pipeline and optional workbook step

The extraction pipeline and converter below are planned, not implemented commands:

1. Ingest native workbook cells or positioned PDF/OCR tokens, retaining coordinates, types, formulas, cached values, display formats and visibility information.
2. Identify relevant pages/tables, reporting periods and units. Interpret column meanings, block structure, row roles and hierarchy from the document itself.
3. Parse source tokens into integer cents in code, preserving the raw signed reading and explicit normalization. Use geometry as well as numeric syntax when separating glued amounts.
4. Check applicable row laws, printed subtotals, year continuity, source pointers and coverage of rows/columns. Re-read ambiguous regions; keep source inconsistencies distinct from uncertain extraction.
5. Serialize the extraction output and validate it with `carth validate-output`.
6. Optionally convert the saved JSON into a copy of [Arbeitsversion-merged-layout-20.xlsx](../challenge/Arbeitsversion-merged-layout-20.xlsx). Conversion consumes the extraction result rather than re-extracting the documents. Put actual assets in `Anlagenverzeichnis` and appropriate summaries in `Gitter nach Anlagenklasse` / `Gitter nach Bilanzposition`, following the [field mapping](REFERENCE.md#core-amount-mapping-corpus-fields-to-actual-workbook-columns). Convert cents to numeric EUR. Preserve printed totals and distinguish derived workbook cells. Keep reporting years separate as described above.

Start with f00, then native Excel and text PDFs, block/summary layouts, and OCR/orientation handling. Evaluate held-out families and layout mutations; their performance is evidence about generalization, not knowledge of the hidden test. Avoid implementing the template's full audit workflow before the batch extraction path works.

## Current implementation and checks

The authoritative application setup is [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock) and [carth/](../carth/). There is text-PDF/Excel ingestion and evaluation tooling, but no complete unattended extraction command or JSON-to-XLSX converter yet. The `ingest` CLI uses corpus keys to discover inputs and writes evidence tokens, not extracted accounting rows; it is a development harness. OCR is not implemented in this stage. Corpus generators have separate dependencies and may delete their output directories; see the [generator reference](REFERENCE.md#8-generator-files-and-development-checks).

Run these existing checks from the repository root:

```sh
uv run carth validate-corpus
uv run python -m unittest discover -s tests -v
```

To inspect the evidence layer for native Excel and text PDFs:

```sh
uv run carth ingest --formats xlsx,pdf
uv run carth recall --formats xlsx,pdf
```

After predictions exist:

```sh
uv run carth validate-output out/pred
uv run carth eval --pred out/pred -v
```

| Command | What it establishes | Limits |
| --- | --- | --- |
| `ingest` | Writes positioned PDF text and Excel-cell tokens to `out/tokens/<doc_id>.json`. | Corpus-key-driven input discovery; no semantic extraction or OCR yet. |
| `recall` | Checks whether keyed amounts can be found in available token files at their source locations. | Development-only evidence coverage; skips missing token files and does not establish semantic extraction accuracy. |
| `validate-corpus` | Ground-truth schema and cross-field validity; defaults to all `*.key.json` under the corpus. | Does not validate extraction outputs or source accuracy. |
| `validate-output` | Extraction schema, abstention/evidence structure, dates, row references and pointer geometry. | No keys needed; does not verify source contents or completeness. |
| `check` | Checks versioned outputs against source evidence and fully observed row laws; also supports legacy predictions. | No extraction-completeness guarantee. OCR-only values require visual verification. |
| `eval` | Local +1/0/−3 comparison of extraction outputs or legacy predictions against keyed standard fields; missing values receive zero and extra values are penalized. | Does not score net movements or independently validate visual OCR evidence. Its pointer tolerances and clipped-text exceptions are local assumptions. |
| `oracle` | Writes predictions copied from keys (or empty rows) for checking the evaluator. | Development-only diagnostic, never an extraction result. Oracle output is not an extraction result and does not satisfy the extraction schema. |

The [reference](REFERENCE.md) holds the corpus inventory, domain distinctions, paired-document relationships, workbook catalogs and sample index. [Open questions](OPEN_QUESTIONS.md) is the single review list for unresolved inconsistencies.
