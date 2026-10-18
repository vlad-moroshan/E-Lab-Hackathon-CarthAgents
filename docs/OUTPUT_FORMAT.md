# Extraction JSON

One input PDF or XLSX produces one `<doc_id>.pred.json`, including all reporting years. The contract is [extraction.schema.json](../carth/output/extraction.schema.json). XLSX conversion is a separate optional step.

The [complete example](examples/example.pred.json) is illustrative, not an extraction from a supplied source. It shows two years, an observed amount, a blank zero and an unreadable value.

## Envelope and metadata

| Property | Contents |
| --- | --- |
| `schema_version` | `"1.0"`. |
| `meta` | Assigned document ID, input format, reporting years and identifiable document facts. |
| `rows` | Logical source rows, including printed subtotals, totals and carry-overs. May be empty with a document-level finding explaining why. |
| `findings` | Detected problems, uncertainties and document-level limitations. Use `[]` when there are none. |

`meta` requires `doc_id`, `format` (`xlsx`, `pdf`, `scan`, `outline`) and `years`. `doc_id` is assigned by the pipeline and must match the `.pred.json` filename. It has no family-prefix requirement. `years` contains every identified reporting year; use `[]` with an explanatory document finding when none can be identified.

Optional metadata: `unit` (`EUR` or `TEUR`), `period_end`, `company`, `doc_type`, `software`, `company_code`. Omit unknown optional facts and explain material uncertainty in findings. Do not invent a company or reporting period. `period_end` is the document's identifiable reporting end, not its print date; individual rows retain their reporting years. For mixed units, omit the document-level unit and use each value's `source_unit`.

Generator facts (`seed`, `invented_names`, `family`, `variant`, pairing/trio information) and `planted` are prohibited. They belong to [ground-truth keys](../carth/eval/corpus.schema.json), not extraction results. `planted` describes deliberately introduced test conditions and expected behavior; `findings` describes what the pipeline actually detects.

## Rows and values

Every row requires `row_id`, `kind`, `level`, `year` and `fields`:

- `row_id` is unique within the document. It identifies findings without relying on uncertain asset IDs.
- `kind` is `asset`, `class_subtotal`, `account_subtotal`, `position_subtotal`, `grand_total`, `carry_over` or `unknown`. `asset` is the existing leaf-row category; `level` gives the actual granularity: `asset`, `account`, `class`, `bilanzposition` or `unknown`. Unknown kind requires `kind_reason`.
- `year` is one of `meta.years`, or null with a `year_reason`. Multiple annual schedules remain separate rows.
- Optional identity fields include `asset_no`, `sub_no`, `class`, `account`, `position`, `name`, `hgb_position`, `acq_date`, `nd_months`, `method`. Omit unavailable identities or use null for nullable text identities. Preserve leading zeros in identifiers.
- `fields` maps semantic field names to value records. An empty field map requires a row-level finding.

Field names retain the corpus meanings: `ahk_open`, `zugang`, `abgang`, `umbuchung`, `zuschreibung`, `ahk_close`, `kum_afa_open`, `afa_gj`, `afa_abgang`, `kum_afa_close`, `bw_close`, `bw_prev`, `abgang_bw`, plus signed net movements `bew_ahk` and `bew_wb`. Net movements use the same value/evidence structure as other amounts; there is no separate `net_fields` property in extraction output.

An observed value looks like:

```json
{
  "amount": 123456,
  "status": "observed",
  "printed": "1.234,56-",
  "raw_amount": -123456,
  "source_unit": "EUR",
  "pointer": {"page": 1, "bbox": [100, 200, 150, 212]}
}
```

`amount` is the semantic output in integer EUR cents. `raw_amount` is the signed code-parsed value in integer EUR cents **after unit scaling, before sign normalization**. The example fits a source column whose negative disposal/depreciation is normalized to a positive magnitude. Transfers and net movements retain their signs; never apply absolute value indiscriminately. A TEUR source token `1` has `raw_amount: 100000`. Numeric fields permit negative integers so source anomalies can be preserved and flagged rather than silently repaired.

`printed`, `raw_amount`, `source_unit` and `pointer` are required for observations. An observed empty amount cell has `printed: ""`, `raw_amount: 0` and `amount: 0`, with a pointer to the identified source amount cell/region. Missing columns and unreadable crops are not zero.

| Status | Amount | Meaning |
| --- | --- | --- |
| `observed` | Integer cents, including zero | Read from source evidence and parsed by code. A printed incorrect subtotal stays observed and receives a finding. |
| `unreadable` | null | A value exists in the source but cannot be read reliably. |
| `absent` | null | The source does not supply this value/column. |
| `not_applicable` | null | The field does not apply to this row/report. |
| `uncertain` | null | Ambiguous reading, units or semantic mapping prevents a supported amount. |

Every non-observed record requires a nonempty `reason`. It may retain partial `printed` text and a pointer where available, but cannot contain a guessed `amount` or `raw_amount`. Omitted fields make no claim about their status; use an explicit record when reporting an identified absence or uncertainty. Derived amounts are not extracted observations and have no value status in this contract.

## Evidence and findings

- PDF evidence: `page` is a 1-based physical page; `bbox` is `[x0, top, x1, bottom]` in PDF points, top-left origin, around the source characters. Convert OCR boxes back to the original page after deskewing/rotation.
- Excel evidence: exact `sheet` and `cell`. Formula text, cached numeric values and displayed strings must remain distinct during ingestion.
- Findings require a descriptive `code`, `severity` (`info`, `warning`, `error`) and `message`. Optional `row_id`, `field` and `pointer` locate the issue. A field finding must reference an existing row and field. Codes are open strings, allowing issues beyond synthetic fixture categories.

## Validation and evaluation

```sh
uv run carth validate-output out/pred
uv run carth validate-output docs/examples/example.pred.json
uv run carth eval --pred out/pred -v
```

Directory validation finds `*.pred.json`; an explicit path can name any JSON file. Validation requires no keys or source documents. It checks the schema, dates, unique row IDs, year membership, finding references, pointer types/geometry, Excel address bounds, and explicit explanations for empty outputs. It does not prove that a pointer actually shows its amount, that signs/units were parsed correctly, or that extraction is complete.

`carth eval` accepts this contract and legacy key-style predictions. It scores observed standard fields; abstentions receive zero. Net movements remain outside its score denominator. It validates versioned outputs before scoring and does not modify them or add ground-truth metadata.

`carth check` supports versioned outputs and legacy key-style predictions. For versioned outputs it checks source cells/boxes and fully observed row laws; reported source inconsistencies remain flagged. OCR-only evidence still needs visual verification. `carth oracle` produces key-derived diagnostics, not extraction results. `carth validate-corpus` validates only ground truth.
