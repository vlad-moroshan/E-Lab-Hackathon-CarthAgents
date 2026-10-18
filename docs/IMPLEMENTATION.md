# Implementation guide

Requirements: [project guide](CHALLENGE_UNDERSTANDING.md). Inventories and template mapping: [reference](REFERENCE.md). Unspecified organiser contracts: [open questions](OPEN_QUESTIONS.md). Fix validation: [REVIEW_FIXES.md](REVIEW_FIXES.md). The two review reports remain evidence of their reviewed snapshots.

## Architecture and milestones

| Stage | Implementation | Remaining work |
| --- | --- | --- |
| Source discovery/ingest | `carth.ingest`: file-type discovery, collision-safe IDs, content fingerprints, original-page PDF boxes and reading frames, native Excel literals and formula/cache state. | General table relevance and layout interpretation. |
| OCR | `carth.ingest.ocr`: per-page invertible cardinal rotations, bounded reading-quality retries, orientation uncertainty, per-document worker failures. | Deskew; fresh CPU performance/accuracy measurements; alternate-engine validation. |
| Lines/records (M5) | Positioned evidence is retained, including glyph boxes for text PDFs. | Automatic section, record and amount-column hypotheses. |
| Layout (M6) | Reviewed reference specs can select token IDs or identified workbook cells. Specs carry the source SHA-256. | Automatic key-free layout discovery and model reference validation. |
| Extraction (M7) | `carth.output.extract` retrieves referenced source values; `source_amount` requires an identified amount column. No financial values are accepted in specs. | Broad layout coverage; safe glued-character splitting. |
| Verification (M8) | Pointer/contract validation, duplicate occurrence prevention, explicit abstentions and evaluation regressions. | Complete source row/column inventory, arithmetic/hierarchy checks and held-out extraction evaluation. |
| Output (M9) | `extraction.schema.json`, `carth.output.write_outputs`, `carth run`: per-value JSON plus a copy of the actual Arbeitsversion. | Organiser confirmation of local schema and workbook conventions. |

Runtime ingestion, parsing, output and CLI imports do not import evaluation modules. Evaluation branches load keys lazily. No runtime path reads keys, generator internals or profiles.

## Commands

```sh
uv run carth ingest INPUT --out out/tokens --types pdf,xlsx
uv run carth ocr INPUT --tokens out/tokens --out out/tokens_ocr --device cpu --workers 1
uv run carth run INPUT out/results --specs out/layouts
uv run python -m unittest discover -s tests -v
uv run carth validate-corpus
uv run python -m carth.numbers
uv run carth oracle --mode evidence --ref-tokens out/tokens_paddle_small --pred out/reference_benchmark
uv run carth eval --pred out/reference_benchmark --ref-tokens out/tokens_paddle_small
```

`run` currently ingests native cells/text. Its layout references are a reviewed intermediate, not an automatic layout detector or an end-to-end hidden-test solution. It does not invoke OCR automatically. Missing layouts produce document-level `needs_layout` flags, both output files, and exit 1. Missing fields produce null values with reason flags. Bad documents are isolated in `_failures.json`. An unreadable input can have a failure diagnostic without a workbook. Completeness cannot be certified merely because a supplied spec omits no fields.

`check` and `recall` require all selected documents by default. `--partial` explicitly requests partial diagnostics. `check` retains the organiser's integrity checks, which cannot establish financial truth or source completeness. `recall` counts missing cache documents as missing values. Neither is an official leaderboard score.

## Layout reference format

Save `<doc_id>.layout.json` in the specs directory. The SHA-256 must match the actual source. A source token ID is retrieved from freshly ingested tokens. For an empty workbook cell, supply a sheet/cell in a positively identified amount column. Cells outside the source area, merged cells and uncached formula/spill ranges cannot establish zero.

```json
{
  "sha256": "<source SHA-256 from ingest>",
  "unit": "EUR",
  "rows": [{
    "id": "source-row-1",
    "year": 2025,
    "kind": "asset",
    "granularity": "asset",
    "asset_no": "printed identifier",
    "name": "printed description",
    "fields": {
      "zugang": {"token": "t42", "amount_column": true},
      "umbuchung": {"sheet": "Sheet1", "cell": "G9", "amount_column": true}
    }
  }]
}
```

Identities are source facts, not generated classifications. Granularity is asset, class, account or position; kind distinguishes leaves, subtotals, totals and carry-overs. No amounts or formula results are accepted in a field reference. IDs and years are not parsed as money outside identified amount columns. Valid NBSP grouping is supported; arbitrary internal spaces are rejected. OCR punctuation repairs and glued alternatives remain flagged rather than resolved by arithmetic. Raw formula expressions never supply amounts; saved caches are retained with their formula provenance and may still be stale.

## Output and workbook conventions

Runtime JSON is separate from `corpus.schema.json`, which still describes supplied fixtures. It has document source/hash, source rows, one `values` record per supplied row/field reference, and flags. Each record carries integer EUR cents or null, precise source pointer, raw text/unit/sign trace and output sheet/cell. Unknown generator metadata is omitted. Blank reasons are mandatory. Schema and cross-record checks run before saving.

The writer copies `challenge/Arbeitsversion-merged-layout-20.xlsx` into the output directory. It retains the 27 template sheets/catalogs and defined names. It writes individual assets into `Anlagenverzeichnis`; summary, subtotal and total rows go into the appropriate class/position grid in source order. Account-level source identities remain accounts; supplemental columns Y/Z identify source granularity and account. Multiple years get separate annual copies of the relevant sheets inside one document workbook. Unknown fiscal end dates remain blank.

Register total `afa_gj` goes into supplemental column AR, labelled as source total, because AC/AD require a supported planned/unplanned split. Book-value disposals use supplemental grid AA/register AS rather than cost disposals. Signed net movements remain separate from gross components; unmapped fields remain in the `Quellwerte` ledger. That ledger also retains all blank/problem records. Cell comments retain source/conversion traces. Imported cells are literal EUR values; unrelated template formulas are not claimed as extracted values and no formula caches are recalculated. Printed errors remain unchanged. Source occurrence reuse is flagged rather than counted twice.

## Reference benchmark

`evidence.py` and `score.py` are evaluation-only heuristics. PDF pointers need finite, positive, ordered, page-bounded geometry, complete reference-token coverage and at most two points of padding per side. Learned column positions use other records in the same page/geometry section; at least three other samples and 80% position agreement are required. Unknown positions, ambiguous repeated values and glued tokens receive no correctness credit. Clipped fields cannot be reconstructed into observed references. No numeric substring fallback is used.

Explicit Excel fields read the actual source cell/cache. Uncached, merged/spill and nonnumeric cells cannot become observed zero. Inferred empty cells require a unique learned field position within the physical record. Unknown columns and net-field positions stay unresolved. Transfer/net signs are retained. Source/key conflicts are counted separately and observed-cell truth determines compliance, so a faithful source value is not punished for disagreeing with an implied key transfer.

Identity includes reporting year, row role, asset/subnumber and printed class/account/position, plus known source level. Unprinted fixture classifications are not required in runtime output; contradictory supplied identities still fail. Unsupported weak/multi references cost −3 if asserted as values. Conservative oracle generation omits them and ambiguous targets. It is a reference-generated benchmark, not a mathematical ceiling, calibrated evidence accuracy or an official result. OCR agreement is not independent pixel verification; learned columns may still be wrong.

## OCR environment and measurements

The current `pyproject.toml`/`uv.lock` declare pinned CPU OCR extras; installation instructions are in the project guide. Dependency/environment changes present during editing were preserved. The core regression suite uses deterministic OCR stubs, not newly installed models.

Existing artifacts `out/tokens_paddle_small/` contain 22 document caches and 113 OCR pages; `out/ocr_small.log` records 914 seconds with two workers. This is a historical run under the former retry policy, not a benchmark of the current implementation. No fresh OCR inference, RSS/model/DPI benchmark or alternate-engine test was performed for these fixes. The portable default is one worker; choose explicit parallelism after measuring available memory on the target environment.
