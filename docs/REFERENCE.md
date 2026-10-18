# Data and workbook reference

Detailed source reference for the CarthAgents hackathon on **18 October 2026**. Start with the [project guide](CHALLENGE_UNDERSTANDING.md) for requirements and implementation status, or the [README](../README.md) for the short overview. Unresolved issues are maintained only in [open questions](OPEN_QUESTIONS.md).

## 1. Source materials and output direction

The [short brief](<../challenge/Challenge 1 - CarthAgents.pdf>), [detailed brief](../challenge/TUM-ai-Challenge-Brief-CarthAgents-detailed.pdf) and [workbook template](../challenge/Arbeitsversion-merged-layout-20.xlsx) live in `challenge/`. The project produces schema-based JSON first; a separate optional step converts it to XLSX. The workbook inventory below describes that export target, not an extraction dependency.

## 2. Repository inventory

Snapshot: **72 paired samples across 10 families**, **4,002 keyed rows**, **36,081 entries in `rows[].fields`**, and **306 additional entries in `rows[].net_fields`**. These are literal key counts, not a verified leaderboard denominator: some printed zero columns and repeated block values are not separately keyed.

| Location | Supplied content | Role |
| --- | --- | --- |
| `challenge/` | Short and detailed challenge PDFs plus `Arbeitsversion-merged-layout-20.xlsx` | Challenge requirements and optional output template. |
| `A3-Hackathon-Corpus/f00_demo/` through `f09_excel_register/` | 72 source documents and 72 matching `.key.json` files | Synthetic development and evaluation corpus. |
| `A3-Hackathon-Corpus/_generator/` | README, four Python utilities, 10 family modules and one shared SAP module | Explains data construction, layouts, planted problems, rendering and key conventions. Not an agent implementation. |
| `A3-Hackathon-Corpus/_intern/profiles/` | 26 Markdown layout profiles | Descriptions of reference layouts that inspired the synthetic corpus. The original client documents described there are not supplied here. |
| `carth/` | Existing top-level Python package: CLI, `ingest/`, `eval/` | Preserve this package structure; dependencies and build configuration live in `pyproject.toml` / `uv.lock`. |
| `carth/eval/` | `score.py`, `official.py`, `recall.py`, `corpus.schema.json`, `validate_corpus.py` | Local scorer, supplied-checker wrapper, evidence recall and key-style JSON contract/validator. See the project guide for their different guarantees. |
| `docs/` | Project guide, this reference and open questions | Requirements and pipeline, detailed source reference and unresolved issues, respectively. |
| `carth/output/` | `extraction.schema.json`, `validate.py` | Extraction output contract and validation without ground truth. |
| `tests/` | Corpus and output schema tests | Whole-corpus acceptance, evidence/abstention validation and evaluator compatibility. |
| `.gitignore` | Python/tooling defaults, macOS metadata, Excel owner/lock files and build-artifact exclusions | Repository housekeeping; it does not establish an application stack. |
| `.DS_Store`, `.git/` | Finder metadata and version-control internals | Not challenge data. |
| `~$*.xlsx` (in demo/other workbook folders) | Small Excel owner/lock artifacts, not ZIP workbooks | Created by Excel, not the generator. Ignore as inputs and in Git; leave active locks on disk while their workbook is open. |

The `carth` Python package provides text-PDF/Excel tokenization, evidence recall, a local scorer/oracle, a supplied-checker wrapper and schema validation. Its `pyproject.toml`, `uv.lock` and `carth/` layout are authoritative for application setup. The output target is [extraction JSON](OUTPUT_FORMAT.md), with optional separate XLSX conversion; neither the complete extraction runner nor converter is implemented. See [the project guide](CHALLENGE_UNDERSTANDING.md) for commands and [open questions](OPEN_QUESTIONS.md) for submission compatibility. Generator code remains separate under the supplied corpus.

### File types and their differences

| Type | Count in corpus | What it contains | Reading implications |
| --- | ---: | --- | --- |
| `.xlsx` | 18 | Native workbooks, including typed numbers/dates, formulas, cached values, text numbers, merged headers and hidden detail | Read every relevant tab and cell, including collapsed rows. Keep formulas, cached values, display formats and hidden draft columns distinct. |
| Text `.pdf` (`meta.format = pdf`) | 34 | Selectable text with coordinates; some deliberately malformed layouts | Preserve token positions; plain text reading order can glue numbers or IDs to descriptions. |
| Scan `.pdf` (`scan`) | 10 | Raster images with skew, blur, noise, fax effects or rotations | Render/OCR with coordinates. Readability is separate from content correctness. |
| Outline `.pdf` (`outline`) | 10 | Crisp vector glyph shapes with **no text layer** | Also needs OCR. A sharp-looking page is not proof that text extraction works. |
| `.key.json` | 72 | Metadata, expected rows, amounts, printed strings, source pointers and planted problems | Use for evaluation only; do not feed these to the extraction pipeline. |
| `.py` | 15 | Corpus generator, renderers and checks | Useful specification evidence; generation has local dependencies and can overwrite output families. |
| `.md` | 27 supplied | Generator README plus 26 profiles | Documentation, not extra source schedules. |

The corpus contains **54 PDFs / 289 pages**. Including the two-page detailed brief and tracked one-page brief, the repository has 56 PDFs / 292 pages and 19 real Excel workbooks. There are no supplied Word, CSV, legacy `.xls` or image files as independent hand-overs, although the brief mentions Word in its real-world motivation and profiles discuss other formats.

Content states are independent of file format: **39 `perfect`, 24 `problem`, 9 `layout-mutation`**. A perfect scan is still difficult to read; “perfect” describes its content, not OCR quality.

## 3. Accounting vocabulary and shared structure

All these schedules describe fixed assets, but they expose different slices of the same history.

| Term | Plain meaning | Common source/key names |
| --- | --- | --- |
| Anlage / Inventar | Individual asset | `asset_no`, `sub_no`, name, acquisition date |
| Anlagenklasse | Asset class, such as machinery or software | `class`, class number/name |
| Sachkonto / Bestandskonto | General-ledger asset account | `account`; preserve leading zeros |
| Bilanzposition | Balance-sheet line grouping accounts/classes | `position`; printed client codes can differ from HGB classification |
| AHK | Acquisition/production cost | `ahk_open`, `ahk_close` |
| Zugang / Abgang | Additions / disposals | `zugang`, `abgang`; distinguish disposal at cost from disposal at book value |
| Umbuchung | Transfer/reclassification | `umbuchung`; signed |
| AfA | Depreciation | `afa_gj`, `kum_afa_open`, `kum_afa_close`, `afa_abgang` |
| Zuschreibung | Reversal of a write-down | `zuschreibung`; reduces accumulated depreciation |
| Buchwert / Restbuchwert | Net carrying value | `bw_prev`, `bw_close`, `abgang_bw` |
| GJ / VJ | Current / prior financial year | Not necessarily calendar years |
| EUR / TEUR | Euro / thousand euro | Convert units explicitly; key integers are cents even for TEUR |
| Übertrag | Repeated running carry-over at a page boundary | Not another asset or an additional business total |
| SuSa / Bilanz / GuV | Trial balance / balance sheet / income statement | Broader audit and reconciliation context in the template/profiles |

### Similarities and distinctions

- **Anlagenspiegel:** a roll-forward, at asset, account, class or balance-sheet-position level. Gross layouts show cost and accumulated depreciation separately; net layouts start from prior book value.
- **Anlagengitter:** often an SAP-style history grid, with flat asset rows or stacked class blocks. A multi-line printed block is one logical record.
- **Anlagenverzeichnis:** an asset register. Some supply a full roll-forward; others supply only closing AHK and book value plus dates/life/method.
- **Zugangs-/Abgangsliste:** additions/disposals only. Described in internal profiles and supported by template tabs, but there is no dedicated additions/disposals corpus family here.
- **Summary and detail may repeat the same economics.** Keep printed rows for evidence/evaluation, but do not add leaf rows, their subtotals and grand totals together.
- **Signs vary by layout.** SAP often prints cost disposals and depreciation negative, with trailing minus. The keys generally normalize those to magnitudes; the workbook also requests positive movements except signed transfers/net movements. Preserve the raw string and signed parsed value alongside any normalized output.
- **Dates vary:** true spreadsheet dates, `DD.MM.YYYY`, `DD.MM.YY`, and header-only periods. A print/run date is not the reporting period.
- **Zero varies:** blank, `0`, `0,00` or `-`. IDs can be text with leading zeros, suffixes or separate subnumbers; never parse them as monetary amounts.

For checking normalized corpus fields, the generator uses:

```text
ahk_close     = ahk_open + zugang - abgang + umbuchung
kum_afa_close = kum_afa_open + afa_gj - afa_abgang - zuschreibung
bw_close      = ahk_close - kum_afa_close
bw_prev       = ahk_open - kum_afa_open
abgang_bw     = abgang - afa_abgang
```

These are checks, not permission to overwrite source values. Only apply a law when its required fields are actually present. The workbook has additional fields, including accumulated-depreciation transfers and separate planned/unplanned depreciation.

## 4. All ten corpus folders

`PDF` below means a text-layer PDF. Scan and outline counts also have the `.pdf` extension. Row/value counts include keyed subtotal/total rows and all represented years.

| Folder | Docs: XLSX / PDF / scan / outline | Key rows / standard values | Meaning and distinctive layout |
| --- | --- | --- | --- |
| `f00_demo` | 4: 1 / 2 / 1 / 0 | 148 / 1,776 | Simple DATEV-like gross roll-forward: assets grouped by class, class subtotals and grand total. Same underlying client in all four renditions. Best first fixture. |
| `f01_net_spiegel` | 8: 1 / 5 / 1 / 1 | 287 / 2,296 | **Account-level net** schedule, no individual assets. Prior BW + movements → closing BW. Position → group → account; group/position sums, normally no grand total. |
| `f02_asset_spiegel` | 7: 1 / 4 / 1 / 1 | 902 / 8,118 | **Asset-level gross** sister of f01. Position → group → optional account → asset. Short IDs and letter suffixes, two-digit acquisition years, method/life, blank zero movements, ID glued to name. |
| `f03_block_spiegel` | 7: 1 / 4 / 1 / 1 | 434 / 5,642 | DATEV-like **three-line AHK / depreciation / BW blocks**. Account-summary section followed by asset detail; repeated/unlabelled totals and repeated movement figures inside blocks. New page per account. |
| `f04_verzeichnis` | 8: 1 / 5 / 1 / 1 | 683 / 1,366 | Portrait **two-amount register**: closing AHK and BW, acquisition/disposal date, cost centre, method, life. Account sums, no grand total. Boxed vs gridless/redacted headers; wrapped names. Does not supply a full movement history. |
| `f05_sap_class_gitter` | 8: 1 / 5 / 1 / 1 | 267 / 3,204 | **Class-level SAP grid**, four-line blocks: identifiers, AHK, AfA, BW. Blue headers, lilac class labels, yellow totals. `*` account, `**` position, `***` business-area, `****` company totals; includes all-zero class. |
| `f06_sap_asset_gitter` | 7: 1 / 3 / 1 / 2 | 462 / 5,082 | **Asset-level SAP grid**, 16 printed columns, portrait pages containing sideways landscape content, selection page and group header. New page per class; class subtotal only. Truncated descriptions and rotated scan pages. |
| `f07_sap_class_summary` | 7: 1 / 4 / 1 / 1 | 153 / 765 | **Class-level SAP depreciation summary**, with position subtotals, no grand total. `Bew AnschWert` / `Bew Wertber` are net movements, not separate additions/disposals. Selection page and orphan last subtotal. Adds 306 `net_fields` values across this family. |
| `f08_excel_spiegel_2y` | 8: 5 / 1 / 1 / 1 | 160 / 1,760 | Handmade **HGB balance-sheet-line roll-forward**, always two years. Current/prior tabs shifted one column; merged headings, real dates, formulas, reconciliation/comments. Not an asset register or true individual-class list. |
| `f09_excel_register` | 8: 5 / 1 / 1 / 1 | 506 / 6,072 | SAP **asset register + class tab**, nine-digit text IDs, subnumbers, hidden/collapsed asset rows, top `SUBTOTAL`, two yellow totals, auditor checks. Text numbers, incomplete transfer column and unrelated forecast variants. |

### Related documents that actually share data

- **f00:** documents 01, 02 and 03 are the same clean table as Excel, text PDF and scan. Document 04 uses the same client with planted problems.
- **f01/f02 pair:** `f01_net_spiegel_03` and `f02_asset_spiegel_02`, seed 150, are the same client/run. Compare class/group and position totals, not row-for-row fields: f01 disposals are **book value**, f02 disposals are **cost**.
- **SAP trio:** documents **01 and 02** in each of f05, f06 and f07 share seed 4711 and the same ledger/year. f06 class subtotals match f05/f07 class leaves. f05/f07 also contain zero-only class `5100`, absent from f06 asset detail. For f07, `bew_ahk = zugang - abgang + umbuchung`, `bew_wb = afa_abgang + zuschreibung`.
- **Multi-year schedules:** all eight f08 files, f01_08 and f07_05 contain two reporting years. Preserve their separate year-tagged rows in the document JSON; see [reporting years](CHALLENGE_UNDERSTANDING.md#reporting-years).
- Other similar-looking files generally use **different seeds/clients**. Matching layout, suffix or company-like labels does not prove shared data.

## 5. Answer-key structure and evaluation traps

Every real corpus document has a sibling `<doc_id>.key.json` with top-level `meta`, `rows`, `planted`.

This shared format is formalized in [carth/eval/corpus.schema.json](../carth/eval/corpus.schema.json), derived from `core.write_key`, family extensions and all 72 supplied keys. Unknown object fields are rejected; family/document names remain open strings so the schema is not tied to the ten current filenames. Optional fields and nullable summary identities are explicit. Standard amount fields are normalized integer cents; net fields and transfers retain their signs.

Run `uv run carth validate-corpus` from the repository root (an optional positional argument selects a file or corpus folder). The package command checks the schema itself, enables date-format validation and adds cross-field checks for row years, matching `fields`/`printed` keys, pointer/flag field references, box ordering and document IDs. It validates all 72 keys / 4,002 rows / 36,081 standard amounts / 306 net amounts. Regression checks: `uv run python -m unittest discover -s tests -v`.

The schema formalizes the **ground-truth answer-key format**. Its synthetic metadata and `planted` annotations are evaluation data, not extraction targets. The separate [extraction schema](../carth/output/extraction.schema.json) supports per-value evidence, abstentions and detected findings; see [Extraction JSON](OUTPUT_FORMAT.md). Structural validation does not prove financial correctness or source-pointer accuracy, and does not replace arithmetic/source checks.

| Part | Contents |
| --- | --- |
| `meta` | Document/family IDs, `doc_type`, `format`, `variant`, unit, years, period end, synthetic company/names and seed; sometimes row level, paired/trio information, company code and SAP position mapping. |
| `rows[]` | Logical row kind, year, asset/subnumber/class/account/position/name where applicable, optional dates/life/method, `fields`, `printed`, `pointer`, and optional flags. |
| `fields` | Integer cents using normalized semantic fields. `umbuchung` may be signed; most depreciation/disposal fields are positive magnitudes. Not every layout prints every possible field. |
| `printed` | Source-style strings corresponding to standard fields, including blank zeros and layout signs. In flagged exceptions, these can differ from normalized truth. |
| `net_fields` | f07's `bew_ahk` and `bew_wb`, signed cents. These are outside the standard `fields` dictionary. |
| Excel `pointer` | `sheet`, row anchor `cell`, and per-field addresses in `cells`. Use the per-field address for value evidence. |
| PDF `pointer` | 1-based physical `page`, line and row/block `bbox` in PDF points, top-left origin. These supplied boxes are usually row/block-wide, not precise value-token boxes. Rotations affect coordinates. |
| `flags` / `planted` | Problem locations, types and intended behavior. `where` can refer to source pointers; `expected_behaviour` explains the planted condition. |

**`kind: asset` does not always mean an individual asset.** It is the evaluator's leaf-row category. f01 leaves have `level: account`, f05/f07 have `level: class`, and f08 has `meta.row_level: bilanzposition`; their asset IDs can be null. Other keyed kinds include `class_subtotal`, `account_subtotal`, `position_subtotal`, `grand_total`, `carry_over`. Headings, blank lines and continuation lines mostly do not become keyed rows.

Problems to handle include glued adjacent amounts, wrapped names, headers only on page 1, carry-overs, multiple years, cover/blank/unrelated pages, TEUR rounding, clipped digits/signs, numbers stored as text, hidden stale columns, stale pasted totals, incomplete transfers and unrelated tables on the same sheet.

### Open integration questions

The single review list is [Open questions](OPEN_QUESTIONS.md). It covers submission compatibility, checker versus scoring semantics, inferred key values, optional workbook representation and OCR/run conditions. The [project guide](CHALLENGE_UNDERSTANDING.md) describes JSON-first output, reporting years and evaluation tools.

## 6. Optional Arbeitsversion export: all 27 tabs

Source: [challenge/Arbeitsversion-merged-layout-20.xlsx](../challenge/Arbeitsversion-merged-layout-20.xlsx). Defined name **`A3_LAYOUT_VERSION = 20`**. All 27 sheets are visible; some columns are hidden. It is a broad, mostly empty audit template with prefilled formulas, not another populated client hand-over. Formula caches in the template are empty; formula text and actual calculated display values must not be confused.

### Working and support tabs

| Tab | Used range | Purpose |
| --- | --- | --- |
| `Offene Punkte` | A1:D4 | Unresolved import questions: tab, location, question, status. Initially says no open points. |
| `Gitter nach Bilanzposition` | A1:X31 | Source roll-forward at balance-sheet-position level; merged AHK/AfA/BW headers, fiscal-end input C2, column headings row 6, units row 7. |
| `Gitter nach Anlagenklasse` | A1:X31 | Same amount columns at asset-class level, plus printed parent position in W. |
| `Anlagenverzeichnis` | A1:AQ508 | 43-column asset register; header row 1, prepared data rows 2–501, checks at 503–508. |
| `Zugänge` | A1:AT501 | 46-column additions list: asset/account, dates, supplier/document, amounts, depreciation and optional supporting evidence/risk fields. Many optional columns hidden. |
| `Abgänge` | A1:AI501 | 35-column disposals list: cost/AfA/BW, proceeds, dates and four arithmetic checks; additional disposal/buyer/approval fields. |
| `Belege` | A1:BU501 | 73-column supporting-document register: invoice/payment/contract, issuer/recipient, dates, tax, cost components, leasing, provenance and reading confidence. |
| `Belegpositionen` | A1:G501 | Seven columns for document line items: key, description, quantity, price, amount, printed asset number, row ID. |
| `Aufwandskonten` | A1:J501 | Ten-column expense-account postings: account, date/text, voucher, counterparty and debit/credit. |
| `Summen- und Saldenliste` | A1:Z510 | 26-column trial balance, source opening/closing balances and debit/credit movements; derived balance/difference/checks, source pointers and groups. Prepared 500-row area plus totals/checks. |
| `Bilanz (§ 266 HGB)` | A1:Q88 | Standard balance-sheet hierarchy, current/prior amounts, subtotal comparisons and client-row links. |
| `Bilanz laut Mandant` | A1:Q7 | Original client balance-sheet structure and source references, before mapping to standard HGB rows. |
| `GuV (§ 275 HGB)` | A1:Q46 | Standard income-statement hierarchy and current/prior checks; includes result appropriation context. |
| `GuV laut Mandant` | A1:Q7 | Original client income-statement structure, amounts and mapping links. |
| `Listen` | A1:P3 | Whole-trial-balance tolerances; P2/P3 are 0.005 EUR. |
| `Auswahllisten` | A1:A53 | 53 supporting-document types, including invoices, approvals, contracts, bank/payment and disposal/existence evidence. |
| `Merge notes` | A1:D148 | Template maintenance notes and formula-ownership constraints. Not client financial data or additional hackathon requirements. |

### Ten schema/catalog tabs

Each field catalog gives **column, stable field ID, display heading, block, required status, type, origin, rule/definition**. Field IDs are scoped to their sheet and are more reliable than display headings. “Ja”, “Soll”, “Nein”, and system/formula fields have different meanings; lack of a required source fact does not authorize inventing it.

| Catalog tab | Range | Describes |
| --- | --- | --- |
| `Feldkatalog Gitter` | A1:H28 | Both grids, 24 column definitions including row ID. |
| `Feldkatalog Anlagenverzeichnis` | A1:H65 | 43 register columns, six arithmetic rules and source-import notes. |
| `Feldkatalog Zugänge` | A1:H50 | 46 additions columns, including signed additions and useful-life units. |
| `Feldkatalog Abgänge` | A1:H39 | 35 disposal columns and check semantics. |
| `Feldkatalog Belege` | A1:H77 | 73 supporting-document columns; percentages are numbers such as 19 for 19%, confidence in basis points. |
| `Feldkatalog Belegpositionen` | A1:H11 | Seven document-item columns. |
| `Feldkatalog Aufwandskonten` | A1:H14 | Ten posting columns and debit/credit rules. |
| `Feldkatalog SuSa` | A1:H46 | 26 trial-balance columns, source sign conventions, subtotal treatment and checks. |
| `Feldkatalog Bilanz GuV HGB` | A1:H21 | 17-column standardized financial statements, part A. |
| `Feldkatalog Bilanz GuV Mandant` | A1:H21 | 17-column source/client statements, part B. |

### Core amount mapping: corpus fields to actual workbook columns

Workbook amounts are numeric **EUR**, whereas key/JSON amount examples use **integer cents**. Normalize signs and scale in code while preserving original evidence. This table guides the optional JSON-to-XLSX conversion; the JSON contract is defined separately in the schema.

| Corpus meaning | Grid column / field ID | Register column / field ID |
| --- | --- | --- |
| `ahk_open` | D / `ahk_01_01` | W / `ahk_01_01` |
| `zugang` | E / `ahk_zugang` | X / `ahk_zugang` |
| `abgang` at cost | F / `ahk_abgang` | Y / `ahk_abgang` |
| `umbuchung` | G / `ahk_umbuchung` | Z / `ahk_umbuchung` |
| `bew_ahk` (net movement) | H / `ahk_bewegung_netto` | No dedicated equivalent |
| `ahk_close` | I / `ahk_31_12` | AA / `ahk_31_12` |
| `kum_afa_open` | J / `afa_01_01` | AB / `afa_01_01` |
| Planned depreciation, when separately identified | K / `afa_gj_plan` | AC / `afa_gj_plan` |
| Total `afa_gj` | L / `afa_gj` | AC + AD only if the source supports that split; do not invent the components |
| Unplanned depreciation | M / `afa_gj_ausserplan` (included in L) | AD / `afa_gj_ausserplan` |
| `afa_abgang` | N / `afa_abgang` | AE / `afa_abgang` |
| `zuschreibung` | O / `zuschreibung` | AF / `zuschreibung` |
| Accumulated-AfA transfer | P / `afa_umbuchung` | AG / `afa_umbuchung` |
| `bew_wb` (net movement) | Q / `afa_bewegung_netto`, with explicit sign conversion | No dedicated equivalent |
| `kum_afa_close` | R / `afa_31_12` | AH / `afa_31_12` |
| `bw_close` | S / `bw_31_12_gj` | AI / `bw_31_12_gj` |
| `bw_prev` | T / `bw_31_12_vj` | AJ / `bw_31_12_vj` |
| Capitalized interest | U / `fk_zinsen` | AK / `fk_zinsen` |

The register's remaining columns are A–D asset/name/class/name-number; E–G HGB classification and printed position number/name; H–J account, cost centre, location; K–Q acquisition, activation, posting, life in years/months, method and depreciation start; R–V residual value, disposal date/type, proceeds and document reference; AL–AP GWG, leasing, rounding allowance, self-created and transaction type; AQ system row ID.

Grid A–C hold classification, printed number and description; V holds row role, W the printed parent position in the class grid, X hidden system row ID. Grid body space is prepared at rows 8–27, with “Summe laut Mandant” at row 28. The field catalogs require retaining the client's own rows/order and amounts. Do not replace a printed total with a recomputed total.

Other important template semantics:

- No subtotal/blank rows inside the flat output asset register; preserve source subtotal evidence separately and in the appropriate grid/JSON records.
- Preserve printed class/position IDs and names independently. Never derive printed HGB position/name from a ledger account. Leave ambiguous classification open.
- Do not treat “davon außerplanmäßig” or capitalized interest as extra amounts to add twice.
- Differentiate system fields, reviewer inputs, directly imported values and formulas/derivations. Hidden `zeilen_id` fields are system identifiers; fresh rows can remain empty there.
- Register formulas prefill closing cost/AfA and BW; checks cover transfer sums, AfA roll-forward, duplicates and range limits. Printed source balances take precedence over derived replacements.
- Other audit tabs are contextual breadth, not evidence that a five-hour solution must implement the whole upstream audit product.

## 7. Internal layout profiles: all 26 files

These notes describe external reference documents, not extra downloadable fixtures. Their page/row counts and vendor guesses describe those originals, **not the synthetic family sizes**. Some mention real-client material not present here; do not fetch or copy it. Their descriptions explain where layout patterns came from.

| File under `_intern/profiles/` | Context and relation |
| --- | --- |
| `7ikk.md` | Summary-only additions/movement report: account and position totals, green-bar bands, redacted period, no asset detail. |
| `Book2.md` | SAP Excel asset register + class grid; hidden outline, top SUBTOTAL, pasted totals, auditor columns and incomplete transfers. Basis for f09. |
| `Book3.md` | Additions list on a sparse 37-column grid with three-line subasset records, dates/IDs as text, amount offset from heading. |
| `Book4.md` | Additions print dump stored one text line per cell in column A; empty first tab, glued page footers and incomplete start/end. |
| `Book5.md` | Five-column trial balance: signed opening balance, debit and credit; no closing balance, period or totals. |
| `Book6.md` | SAP disposals Excel: two data lines + two spacer rows; cost/AfA/BW, proceeds/gain/loss, missing asset-number column. |
| `Book7.md` | Another five-column trial balance; shorter numeric accounts lose leading zeros, blank movement cells and bold opening balances. |
| `Sthg.md` | Handmade two-year HGB roll-forward with shifted tabs, merged headings, formulas, reconciliation/comments. Basis for f08. |
| `aasdaswd.md` | Net account-level schedule with custom position/group/account hierarchy and cent drift. Basis for f01; sibling of asdasd. |
| `arbeitblatt.md` | Broad audit workpaper: lead schedule, reconciliations, additions/disposals tests, prose/screenshots/ink; not a clean input register. |
| `asdasd.md` | Gross asset-level sister of aasdaswd; ID/name glue, suffixes, wrapped names, blank movements and repeated sums. Basis for f02. |
| `asxa.md` | Annual-accounts package with Bilanz/GuV/account evidence; no asset schedule. Reconciliation context only. |
| `asxasx.md` | DATEV-like disposal summary + detail, account-prefixed asset IDs, cost and book-value disposal/proceeds. Related to dsfdvfdvd. |
| `dsfdvfdvd.md` | DATEV-like summary then asset detail in AHK/AfA/BW blocks, second-line negatives, unlabelled totals. Basis for f03. |
| `ertgerg.md` | SAP disposals as rotated vector-outline PDF, four-line asset boxes, statistics cover and trailing-minus signs. |
| `everv.md` | ERP tax-view disposals, account sums only, residual BW, wrapped/glued fields; related to qsxqsx and qsqxsxqsx. |
| `qsqxsxqsx.md` | ERP additions sister of everv; empty opening cost, addition amounts, duplicated description/posting text, account sums. |
| `qsxqsx.md` | Ruled portrait ERP register with closing AHK/BW, dates/method/life and account sums. Basis for f04. |
| `qsxqsxq.md` | Same reference register as qsxqsx, gridless/redacted reprint with clipped period year. Basis for f04's alternate rendering. |
| `qwdqwd.md` | Balance-sheet and income-statement excerpt, mixed orientation, carry-overs; no asset schedule. |
| `rrtvr.md` | Sideways outlined SAP asset history grid, class headers/subtotals, truncated descriptions. Basis for f06. |
| `rtv.XLSX.md` | Despite the name, describes a text PDF of an Excel/SAP class grid: four-line blocks, star totals, cut right edge. Basis for f05. |
| `saxqawxq.md` | Outlined SAP Bilanz/GuV, mixed rotations and redaction; ties to reference SAP ledger, not an asset schedule itself. |
| `wedqwdq.md` | Annual accounts with non-calendar year and separate cost/depreciation accounts; useful tie-out context, no schedule. |
| `zt.md` | SAP class depreciation summary with net movements, position sums and orphan last subtotal. Basis for f07. |
| `zunzun.md` | Sideways outlined SAP additions: asset headers → postings, discounts/negative lines and two amount positions. Reference ledger sibling of rrtvr/zt; no dedicated generated family here. |

## 8. Generator files and development checks

Paths below are relative to `A3-Hackathon-Corpus/_generator/`.

| File | Purpose |
| --- | --- |
| `README.md` | Generator commands, family contract and order of problem injection. |
| `core.py` | Invented asset/client histories, cent arithmetic, classes, formatting, table/row model, Excel/PDF/scan/outline renderers, problem injections and JSON-key writing; data-law self-check. |
| `make_corpus.py` | Discovers family modules, builds selected/all families, then checks the output. **Deletes each selected output family folder before rebuilding.** |
| `check_corpus.py` | Checks row laws, subtotal sums, Excel source pointers, text-PDF amounts, absence of text in scan/outline PDFs, and invented-name separation from original client files. Implements integrity checks, not a +1/0/−3 completeness score. Use the application wrapper for prediction checks. |
| `selftest.py` | Builds seven temporary fixtures to exercise renderers/problem types and runs corpus checks. |
| `families/f00_demo.py` | Baseline table and four demo renditions; documents the family interface. |
| `families/f01_net_spiegel.py` | Net account layout, client tree/IDs/shared f02 helpers, rounding drift and mutations. |
| `families/f02_asset_spiegel.py` | Gross asset sister layout, ID/name glue and alternate flat layout. |
| `families/f03_block_spiegel.py` | Custom three-line summary/detail renderer and matching line-oriented Excel export. |
| `families/f04_verzeichnis.py` | Ruled/gridless portrait register, variable-height wrapped cells and redaction. |
| `families/_sap_common.py` | Shared SAP ledger, signs, identifiers, selection/group pages, boxed rendering, rotations/clipping and trio check. |
| `families/f05_sap_class_gitter.py` | Four-line class blocks and matching colored Excel rendering. |
| `families/f06_sap_asset_gitter.py` | Sideways asset grid, group headers, class breaks and truncated names. |
| `families/f07_sap_class_summary.py` | Class-level net movement columns and selection/orphan-subtotal layout. |
| `families/f08_excel_spiegel_2y.py` | Two-year formula workbooks, merged/date headers, stale/hidden data, comments and recalculation. |
| `families/f09_excel_register.py` | Asset/class Excel layouts, hidden outlines, text numbers, transfer gaps and extra forecast table. |

The generator uses Python with `openpyxl`, Pillow, ReportLab and `pdfplumber`; external Poppler, Ghostscript and LibreOffice plus macOS fonts are required by some paths. Several paths are hard-coded (`/opt/homebrew/bin/gs`, `/opt/homebrew/bin/soffice`, Supplemental Arial fonts). The application dependency setup in `pyproject.toml` / `uv.lock` does not supply every generator prerequisite. Do not confuse generator requirements with the application package.

Documented read-only check commands, **from `A3-Hackathon-Corpus/`**, once prerequisites are available:

```sh
python3 -I _generator/core.py
python3 -I _generator/check_corpus.py .
python3 -I _generator/families/_sap_common.py .
```

`check_corpus.py` also expects original-client folders under `~/Desktop/Client-Files-Confidential/{anonyaa,anony}` for its name-separation check. Those files are not supplied; the full checker is not portable as written. Do not seek private client folders just to make it pass. `selftest.py` inherits that dependency. To experiment with generation, choose a fresh output directory outside the supplied corpus; never rebuild into the original data by default.

## Appendix: every supplied sample

Each linked document has a matching `<doc_id>.key.json` in the same folder. `pdf` = text layer; `scan`/`outline` = PDF without a text layer. `perfect` describes clean content; `layout-mutation` changes the layout. Years are financial-year labels, not an assertion of December year-end.

| Document | Format / content | Years; unit | Key rows | Problems / context |
| --- | --- | --- | ---: | --- |
| [f00_demo_01](../A3-Hackathon-Corpus/f00_demo/f00_demo_01.xlsx) | xlsx / perfect | 2025; EUR | 37 | Clean source |
| [f00_demo_02](../A3-Hackathon-Corpus/f00_demo/f00_demo_02.pdf) | pdf / perfect | 2025; EUR | 37 | Clean source |
| [f00_demo_03](../A3-Hackathon-Corpus/f00_demo/f00_demo_03.pdf) | scan / perfect | 2025; EUR | 37 | Clean source |
| [f00_demo_04](../A3-Hackathon-Corpus/f00_demo/f00_demo_04.pdf) | pdf / problem | 2025; EUR | 37 | glued_numbers, non_tying_subtotal |
| [f01_net_spiegel_01](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_01.pdf) | scan / perfect | 2025; EUR | 33 | Clean source |
| [f01_net_spiegel_02](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_02.pdf) | pdf / problem | 2025; EUR | 33 | non_tying_subtotal, wrapped_description |
| [f01_net_spiegel_03](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_03.pdf) | pdf / perfect | 2025; EUR | 33 | Paired with f02_asset_spiegel_02 |
| [f01_net_spiegel_04](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_04.pdf) | pdf / layout-mutation | 2025; EUR | 23 | Clean source |
| [f01_net_spiegel_05](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_05.pdf) | outline / perfect | 2025; EUR | 33 | Clean source |
| [f01_net_spiegel_06](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_06.pdf) | pdf / problem | 2025; EUR | 33 | glued_numbers, noise_page_cover |
| [f01_net_spiegel_07](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_07.xlsx) | xlsx / perfect | 2025; EUR | 33 | Clean source |
| [f01_net_spiegel_08](../A3-Hackathon-Corpus/f01_net_spiegel/f01_net_spiegel_08.pdf) | pdf / problem | 2024, 2025; EUR | 66 | multi_year |
| [f02_asset_spiegel_01](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_01.pdf) | pdf / problem | 2025; EUR | 112 | wrapped_description, non_tying_subtotal |
| [f02_asset_spiegel_02](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_02.pdf) | pdf / perfect | 2025; EUR | 137 | Paired with f01_net_spiegel_03 |
| [f02_asset_spiegel_03](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_03.xlsx) | xlsx / perfect | 2025; EUR | 135 | Clean source |
| [f02_asset_spiegel_04](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_04.pdf) | outline / perfect | 2025; EUR | 123 | Clean source |
| [f02_asset_spiegel_05](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_05.pdf) | pdf / layout-mutation | 2025; EUR | 121 | Clean source |
| [f02_asset_spiegel_06](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_06.pdf) | scan / perfect | 2025; EUR | 135 | Clean source |
| [f02_asset_spiegel_07](../A3-Hackathon-Corpus/f02_asset_spiegel/f02_asset_spiegel_07.pdf) | pdf / problem | 2025; EUR | 139 | glued_numbers, non_tying_subtotal, noise_page_blank |
| [f03_block_spiegel_01](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_01.pdf) | pdf / perfect | 2025; EUR | 61 | Clean source |
| [f03_block_spiegel_02](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_02.xlsx) | xlsx / perfect | 2024; EUR | 63 | Clean source |
| [f03_block_spiegel_03](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_03.pdf) | scan / perfect | 2025; EUR | 59 | Clean source |
| [f03_block_spiegel_04](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_04.pdf) | outline / perfect | 2025; EUR | 70 | Clean source |
| [f03_block_spiegel_05](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_05.pdf) | pdf / problem | 2025; EUR | 50 | glued_numbers, non_tying_subtotal |
| [f03_block_spiegel_06](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_06.pdf) | pdf / problem | 2024; EUR | 72 | header_only_on_first_page, noise_page_cover |
| [f03_block_spiegel_07](../A3-Hackathon-Corpus/f03_block_spiegel/f03_block_spiegel_07.pdf) | pdf / layout-mutation | 2025; EUR | 59 | Clean source |
| [f04_verzeichnis_01](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_01.pdf) | pdf / perfect | 2025; EUR | 84 | Clean source |
| [f04_verzeichnis_02](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_02.pdf) | pdf / perfect | 2025; EUR | 85 | Clean source |
| [f04_verzeichnis_03](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_03.xlsx) | xlsx / perfect | 2024; EUR | 95 | Clean source |
| [f04_verzeichnis_04](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_04.pdf) | scan / perfect | 2025; EUR | 77 | Clean source |
| [f04_verzeichnis_05](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_05.pdf) | outline / perfect | 2025; EUR | 85 | Clean source |
| [f04_verzeichnis_06](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_06.pdf) | pdf / problem | 2025; EUR | 82 | wrapped_description, non_tying_subtotal |
| [f04_verzeichnis_07](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_07.pdf) | pdf / problem | 2024; EUR | 93 | header_only_on_first_page, noise_page_unrelated |
| [f04_verzeichnis_08](../A3-Hackathon-Corpus/f04_verzeichnis/f04_verzeichnis_08.pdf) | pdf / layout-mutation | 2025; EUR | 82 | Clean source |
| [f05_sap_class_gitter_01](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_01.pdf) | pdf / perfect | 2025; EUR | 33 | Shared SAP trio ledger |
| [f05_sap_class_gitter_02](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_02.xlsx) | xlsx / perfect | 2025; EUR | 33 | Shared SAP trio ledger |
| [f05_sap_class_gitter_03](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_03.pdf) | scan / perfect | 2025; EUR | 30 | Clean source |
| [f05_sap_class_gitter_04](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_04.pdf) | outline / perfect | 2024; EUR | 36 | Clean source |
| [f05_sap_class_gitter_05](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_05.pdf) | pdf / problem | 2025; EUR | 34 | column_cut_off |
| [f05_sap_class_gitter_06](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_06.pdf) | pdf / problem | 2025; TEUR | 32 | teur_rounding, non_tying_subtotal |
| [f05_sap_class_gitter_07](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_07.pdf) | pdf / problem | 2025; EUR | 33 | glued_numbers, header_only_on_first_page, noise_page_blank |
| [f05_sap_class_gitter_08](../A3-Hackathon-Corpus/f05_sap_class_gitter/f05_sap_class_gitter_08.pdf) | pdf / layout-mutation | 2025; EUR | 36 | Clean source |
| [f06_sap_asset_gitter_01](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_01.pdf) | outline / perfect | 2025; EUR | 88 | Shared SAP trio ledger |
| [f06_sap_asset_gitter_02](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_02.xlsx) | xlsx / perfect | 2025; EUR | 88 | Shared SAP trio ledger |
| [f06_sap_asset_gitter_03](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_03.pdf) | scan / perfect | 2025; EUR | 50 | Clean source |
| [f06_sap_asset_gitter_04](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_04.pdf) | pdf / problem | 2025; EUR | 67 | glued_numbers, non_tying_subtotal, carry_over |
| [f06_sap_asset_gitter_05](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_05.pdf) | outline / problem | 2024; EUR | 57 | header_only_on_first_page, noise_page_unrelated |
| [f06_sap_asset_gitter_06](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_06.pdf) | pdf / problem | 2025; EUR | 49 | column_cut_off |
| [f06_sap_asset_gitter_07](../A3-Hackathon-Corpus/f06_sap_asset_gitter/f06_sap_asset_gitter_07.pdf) | pdf / layout-mutation | 2025; EUR | 63 | Clean source |
| [f07_sap_class_summary_01](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_01.pdf) | pdf / perfect | 2025; EUR | 18 | Shared SAP trio ledger |
| [f07_sap_class_summary_02](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_02.xlsx) | xlsx / perfect | 2025; EUR | 18 | Shared SAP trio ledger |
| [f07_sap_class_summary_03](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_03.pdf) | scan / perfect | 2025; EUR | 20 | Clean source |
| [f07_sap_class_summary_04](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_04.pdf) | outline / perfect | 2025; EUR | 19 | Clean source |
| [f07_sap_class_summary_05](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_05.pdf) | pdf / problem | 2024, 2025; EUR | 40 | multi_year, non_tying_subtotal |
| [f07_sap_class_summary_06](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_06.pdf) | pdf / problem | 2025; TEUR | 18 | teur_rounding, glued_numbers, noise_page_cover |
| [f07_sap_class_summary_07](../A3-Hackathon-Corpus/f07_sap_class_summary/f07_sap_class_summary_07.pdf) | pdf / layout-mutation | 2024; EUR | 20 | Clean source |
| [f08_excel_spiegel_2y_01](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_01.xlsx) | xlsx / perfect | 2024, 2025; EUR | 20 | multi_year |
| [f08_excel_spiegel_2y_02](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_02.pdf) | pdf / perfect | 2024, 2025; EUR | 20 | multi_year |
| [f08_excel_spiegel_2y_03](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_03.pdf) | scan / perfect | 2023, 2024; EUR | 20 | multi_year |
| [f08_excel_spiegel_2y_04](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_04.pdf) | outline / perfect | 2024, 2025; EUR | 20 | multi_year |
| [f08_excel_spiegel_2y_05](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_05.xlsx) | xlsx / problem | 2024, 2025; EUR | 20 | multi_year, numbers_as_text |
| [f08_excel_spiegel_2y_06](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_06.xlsx) | xlsx / problem | 2024, 2025; EUR | 20 | multi_year, non_tying_subtotal |
| [f08_excel_spiegel_2y_07](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_07.xlsx) | xlsx / problem | 2024, 2025; EUR | 20 | multi_year, hidden_column |
| [f08_excel_spiegel_2y_08](../A3-Hackathon-Corpus/f08_excel_spiegel_2y/f08_excel_spiegel_2y_08.xlsx) | xlsx / layout-mutation | 2024, 2025; EUR | 20 | multi_year |
| [f09_excel_register_01](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_01.xlsx) | xlsx / perfect | 2025; EUR | 74 | Clean source |
| [f09_excel_register_02](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_02.pdf) | pdf / perfect | 2025; EUR | 62 | Clean source |
| [f09_excel_register_03](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_03.pdf) | scan / perfect | 2025; EUR | 75 | Clean source |
| [f09_excel_register_04](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_04.pdf) | outline / perfect | 2024; EUR | 63 | Clean source |
| [f09_excel_register_05](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_05.xlsx) | xlsx / problem | 2025; EUR | 66 | transfer_breaks_cost_law |
| [f09_excel_register_06](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_06.xlsx) | xlsx / problem | 2025; EUR | 46 | numbers_as_text |
| [f09_excel_register_07](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_07.xlsx) | xlsx / problem | 2025; EUR | 59 | unrelated_table |
| [f09_excel_register_08](../A3-Hackathon-Corpus/f09_excel_register/f09_excel_register_08.xlsx) | xlsx / layout-mutation | 2025; EUR | 61 | Clean source |
