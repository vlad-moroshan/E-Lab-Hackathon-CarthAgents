# Open questions

Schema gaps, evaluation limitations and unspecified export requirements for the [extraction pipeline](CHALLENGE_UNDERSTANDING.md).

## 1. JSON schema versus extraction output

The strict [schema](../carth/eval/corpus.schema.json) describes complete synthetic fixtures:

- `rows` and `fields` must be nonempty; amounts cannot be null. There is no general unreadable/absent/not-applicable status, uncertainty reason or empty-document representation.
- `meta` requires `seed`, `invented_names`, `company`, `family` and a known `variant`; the validator also requires `doc_id` to start with `family + '_'`. Generator-only facts are unavailable from unfamiliar documents and must not be fabricated or copied from keys.
- `flags` allows only `glued`, `non_tying`, `cut_off`, `transfer_incomplete`; additional properties are rejected. Arbitrary diagnostics and per-value `pointers` are not allowed. The local scorer nevertheless accepts null amounts and per-value `pointers`.
- f07 `net_fields` has no corresponding per-field printed-text/cell-pointer contract, although every value needs evidence.

An extraction-specific schema or extension is needed for abstentions, diagnostics, unknown metadata and per-value evidence. Omitting an amount alone does not satisfy explicit flagged abstention.

## 2. Scoring and evidence

`_generator/check_corpus.py` is an integrity checker, with no +1/0/−3 score or answer-key completeness comparison. The wrapper [official.py](../carth/eval/official.py) exposes it as `carth check`; [score.py](../carth/eval/score.py) implements a separate local scoring approximation.

The local scorer matches by source location rather than independently checking row identity/year, allows 1.5-point PDF row-box slack, skips text checking for `cut_off`, and counts only standard `fields`. The supplied checker searches printed strings anywhere on a text-PDF page, skips flagged Excel fields and compares numeric magnitudes; it does not prove precise per-value provenance. Neither tool verifies OCR amounts against pixels. `check` also skips missing prediction files.

The judging rules for row matching, missing/extra rows, net fields, flags, bounding-box precision and rotated-page coordinates are unspecified. Required submission filenames are also unspecified; `.pred.json` is the local convention. Report `eval` results as local scores and checker success within these limits.

## 3. Printed values versus inferred answer-key values

f05_05 and f06_06 ask for clipped amounts reconstructed from row laws. f09_05 stores an implied transfer where the source shows zero, with affected totals also flagged. This conflicts with the brief's rule to report what is printed with supporting evidence.

Credit for derived amounts and the required dependency-evidence format are unspecified. Retain observed values, flag inconsistencies, and abstain on unreadable amounts. Keep derived diagnostics distinct; an empty or clipped cell is not direct evidence for a reconstructed figure.

## 4. Optional workbook representation

The template has `Gitter nach Anlagenklasse` and `Gitter nach Bilanzposition` sheets. Conversion has these limitations:

- The core sheets represent one reporting year with prior-year comparisons. JSON supports multiple reporting years, and 10 supplied documents contain two full annual schedules. The converter needs a target year or separate annual workbooks; the export convention is unspecified. See [reporting years](CHALLENGE_UNDERSTANDING.md#reporting-years).
- The register splits planned/unplanned depreciation, while some sources provide only total `afa_gj`. Net-only movements cannot reveal gross components. Missing breakdowns must remain unresolved.
- Template formulas and catalogs allow derivations, while `Merge notes` row 141 contains a conflicting “structure only” statement. Formula handling must preserve printed balances and distinguish derived values.

## 5. OCR and run conditions

Model OCR is allowed, but acceptable generative vision transcription methods are unspecified. Preserve token evidence and parse amounts in code; layout interpretation must not invent financial values.

API/network availability, runtime/cost limits, individual-document versus client-bundle evaluation, and input formats beyond the supplied PDF/XLSX corpus are unspecified. Hidden tests use unseen layouts; their relationship to the supplied generator is unknown.
