# CarthAgents Challenge: Understanding & Assumptions

Sources read: `Challenge 1 - CarthAgents.pdf`, all of `A3-Hackathon-Corpus/_generator/` (core, check_corpus, selftest, the 10 families + `_sap_common`), all 72 answer keys (stats), `_intern/profiles/*.md`.

## 1. The task in one paragraph

A client sends its auditor a **fixed-asset roll-forward** (Anlagenspiegel / Anlagengitter / Anlagenverzeichnis) in some random export format. We must turn it into the auditor's standard workbook (**Arbeitsversion**): tab *Anlagenverzeichnis* = one row per asset, tab *Anlagengitter* = one row per asset class. Every number must be copied (by code, not by an LLM) from the document, carry a pointer to where it was printed, and the system must abstain where it is unsure.

## 2. The domain (what a row means)

Every row, asset or total, is the same 12/13-number roll-forward. Amounts are int cents, keys store **magnitudes** (signs are layout). Only `umbuchung` may be negative.

| field | German print labels (examples) | meaning |
|---|---|---|
| `ahk_open` | AHK GJ-Beg, Stand zum 01.01., Anfangsstand, AK/HK | historical cost at start |
| `zugang` | Zugänge | additions |
| `abgang` | Abgänge (at cost) | disposals at cost |
| `umbuchung` | Umbuchungen | transfers (sum to 0 across the whole doc) |
| `zuschreibung` | Zuschreibungen | write-ups |
| `ahk_close` | aktuelle AHK, Stand zum 31.12., Endstand | cost at end |
| `kum_afa_open` | AfA GJ-Beg, kum. Abschreibungen 01.01. | accumulated depreciation at start |
| `afa_gj` | AfA des Jahres, Abschreibung GJ, Normal-AfA | depreciation this year |
| `afa_abgang` | AfA Abgang | depreciation removed on disposal |
| `kum_afa_close` | kumulierte AfA, Abschreibungen (kumuliert) | accumulated depreciation at end |
| `bw_prev` | Buchwert Vorjahr, Restbuchwert 01.01. | book value at start |
| `bw_close` | lfd Buchwert, Buchwert 31.12., RBW | book value at end |
| `abgang_bw` | Abgang zum Restbuchwert (net layouts only) | disposal at book value |

**Laws** (`check_corpus.LAWS`), our main checking tool:
- `ahk_close = ahk_open + zugang − abgang + umbuchung`
- `kum_afa_close = kum_afa_open + afa_gj − afa_abgang − zuschreibung`
- `bw_close = ahk_close − kum_afa_close`, `bw_prev = ahk_open − kum_afa_open`
- net form: `bw_close = bw_prev + zugang + umbuchung − abgang_bw − afa_gj + zuschreibung`
- subtotal = sum of its child rows (unless the client's sum is broken, which is a planted flag)
- multi-year: closing of year N−1 = opening of year N

Hierarchy (HGB § 266 / SKR03): **HGB position** (A.I.2, A.II.1 to 4, A.III.3) > **account** (0027, 0210, …) > **class** (1000, 3000, …) > **asset** (asset_no + sub_no). 13 classes in the catalog (`core.CATALOG`). SAP layouts use 7-digit Bilanzpositionen (`2102200` = A.II.2).

## 3. What the corpus is

72 documents in 10 families (`f00` to `f09`), each with a `.key.json` answer key. Formats: 21 xlsx, 34 text PDF, 10 scans (image only), 10 "outline" PDFs (vector glyphs, **no text layer**, so OCR is needed). In total ~20 of 72 docs need OCR.

| family | what it imitates | leaf row level |
|---|---|---|
| f00 demo | plain DATEV-like Spiegel | asset |
| f01 net_spiegel | net Spiegel (book value view), account level, 3 heading levels | account |
| f02 asset_spiegel | gross per-asset, id glued to name in the text layer | asset |
| f03 block_spiegel | DATEV "Entwicklung des AV": **3-line blocks** per asset, negatives on a 2nd line | asset |
| f04 verzeichnis | register: only AHK + Buchwert, dates, AfA code, ND | asset |
| f05 sap_class_gitter | SAP ALV 4-line boxed records, star-levels `*`, `**` | class |
| f06 sap_asset_gitter | SAP per asset, **page rotated 90°**, outline PDF | asset |
| f07 sap_class_summary | SAP, net columns `Bew AnschWert`, `Bew Wertber` | class |
| f08 excel_spiegel_2y | hand-made Excel, two years on two tabs, formulas | HGB position |
| f09 excel_register | SAP export edited by auditor, hidden outline rows, SUBTOTAL rows | asset |

Each family has variants: **perfect**, **problem** (planted defects), **layout-mutation** (same data, renamed / reordered columns, other sign style). That mutation variant is the organisers' simulation of the "unseen layouts" of the final test.

### Planted problems (what the scorer tests for)

| problem | right behaviour |
|---|---|
| `glued_numbers` `12.977,004.076,11` | split into the two adjacent columns |
| `non_tying_subtotal` | report the **printed** value, flag the difference (rule 05) |
| `wrapped_description` | join the continuation line, it is not a row |
| `carry_over` (Übertrag) | not an asset and not a total |
| `header_only_on_first_page` | keep page-1 column mapping |
| `noise_page_*` (cover letter, blank, unrelated Kontennachweis) | ignore |
| `teur_rounding` | amounts in thousands, rounded one by one; sums are off by rounding |
| `multi_year` | tag each row with its year |
| `column_cut_off` | last column loses its last 4 characters at the page edge; the key says "rebuild from row laws" |
| `numbers_as_text` (`1.234,56-`) | parse German text and trailing minus |
| `hidden_column` (old draft) | ignore hidden columns |
| `unrelated_table` below the register | ignore |
| `transfer_breaks_cost_law` | Umbuchung cell empty; the key holds the *implied* value, flagged |

Number styles seen: `1.234,56` · `1234,56` · `1.234,56-` · `(1.234,56)` · `1,234.56` · TEUR `1.235`; zeros as `""`, `0,00`, `-`. Dates `31.12.2025`, `31.12.25`, ISO, `12/2025`. Fiscal years can end 30.06, 30.09 or 31.03.

### Answer key = the scoring unit

Each keyed row has `kind` (asset / class_subtotal / account_subtotal / position_subtotal / grand_total / carry_over), identity (`year, asset_no, sub_no, class, account, position, name`), `fields` (cents), `printed` (exact string), `pointer` (`{page, line, bbox}` for PDFs, bbox in **points, top-left origin, like pdfplumber**; `{sheet, cell, cells{field: coord}}` for xlsx) and `flags`. So the unit we are scored on is roughly a **(row, field) value + pointer**: ~3,800 keyed rows × ~10 fields in the training corpus.

## 4. Intuition about the scoring

+1 correct / 0 blank / −3 wrong means **a value is only worth writing if P(correct) > 75 %**. Coverage alone does not help; calibrated abstention is the game. A system that gets 90 % of the values right and writes everything scores 0.9 − 0.3 = 0.6 per value. If it can tell the risky 10 % apart and blank them, it scores ~0.9.

We have a strong, free source of confidence: the **accounting laws**. A row whose 5 identities close to the cent, inside a subtotal that ties, was almost certainly read right (OCR errors and column shifts break the laws). This is also rule 03 ("checks for accuracy *and completeness*"): completeness = Σ assets = printed class totals = grand total, so no missing rows.

"A value whose pointer does not show it counts as wrong": the pointer is part of the answer. Derived or "fixed" values have no honest pointer, so we should almost never invent numbers.

## 5. Assumptions (to confirm with the organisers, marked ❓)

1. ❓ **The empty Arbeitsversion template and the scorer are NOT in this repo.** The brief says we get them. We need both before building the output writer; until then the `.key.json` schema is our proxy for the output schema.
2. ❓ Row matching: probably by `(year, asset_no, sub_no)` for assets and `(kind, year, class/account/position)` for totals. It decides how much identity extraction matters.
3. ❓ Pointer tolerance: does the bbox need to overlap the key's row bbox, or just page + line? For xlsx, the exact cell.
4. ❓ Class-level docs (f05/f07/f08/f01) fill only the *Anlagengitter* tab. Per-asset docs fill *Anlagenverzeichnis*. Do we also fill Anlagengitter for them, from printed class subtotals only, or from code sums (which have no single pointer)? Safer default: use printed subtotals only.
5. ❓ Flagged fields (`glued`, `cut_off`, `non_tying`, `transfer_breaks_cost_law`): scored normally, or excluded? The cut-off and transfer cases ask for law-derived values. That conflicts with "read, never judge", so we need the organisers' ruling. Default: the code may derive a value **only** from a law with all other terms read, write it with the pointer of the truncated / empty cell, and flag it.
6. Rule 01 means the LLM must not transcribe digits. So **GPT-vision cannot read numbers off scans**. OCR (Tesseract / PaddleOCR / docTR, all "code") must produce the numerals with bboxes. The LLM may decide *structure*: which column is `afa_gj`, which row is a subtotal, which page is noise, which class maps to which HGB position.
7. Signs: we output magnitudes as the key does (except `umbuchung`). The printed sign only tells us which column it is.
8. TEUR docs: report as printed × 1000 EUR (key stores `round_teur` cents); sum checks need a ± 0.5 TEUR per term tolerance.
9. The hidden test = the same generator with **new families**. The `_intern/profiles` are descriptions of the real hand-overs the families copy; the ones not yet used as families are the best guess for the hidden layouts: SAP per-asset Gitter (`rrtvr`), wide-grid ERP export (`Book3`), **one-text-column dump** (`Book4`), Zugangsliste / Abgangsliste (`zunzun`, `qsqxsxqsx`, `everv`, `Book6`: only part of the fields), Word files (brief mentions .docx; none in the corpus). Non-asset docs (SuSa, Bilanz/GuV: `Book5/7`, `qwdqwd`, `saxqawxq`) may come as distractors and should produce **nothing**.
10. Tooling: `pdftoppm` is installed. `pdfplumber`, `tesseract` and `soffice` are not (check_corpus needs pdfplumber).
11. ❓ Zeros: a correct `0` (including a blank movement cell that means 0) scores +1, so we write zeros explicitly rather than leaving them empty.
12. ❓ Totals: we assume subtotal and total rows are scored too (they are keyed). Carry-over lines are keyed but are neither assets nor totals.
13. ❓ Each file is processed on its own; checks across related files are optional extras, never needed for the output.
14. ❓ Run conditions are unknown (time / cost per document, submit code or outputs, API access during the final run). We design for an offline-capable pipeline where the LLM steps are cached per layout.

All ❓ items are collected as questions for the organisers in §7.

## 5b. Refinements after cross-review with a second analysis

The second analysis only saw the brief and the generator code, not the corpus, keys or profiles. These points from it hold up (checked against code and keys) and are now part of our model:

- **"Leaf row" ≠ asset.** In the keys, `kind: "asset"` means *the finest row this document prints*: an account (f01), a class (f05/f07, `level: "class"`) or an HGB line item (f08, `row_level: "bilanzposition"`). Our row classifier must decide the **granularity** first. The output tab then follows from it: only real assets go to *Anlagenverzeichnis*.
- **Column names are not stable meanings.** "Abgänge" is `abgang` (at cost) in gross layouts and `abgang_bw` (at book value) in net layouts (f01, the BW line of f03). The layout type (gross / net) must be decided before mapping columns, and the laws tell the two apart (net form vs. gross form closes).
- **Visibility ≠ relevance.** f09 keeps every asset row in **hidden outline rows**: they must be read. f08_07 has a **hidden stale draft column**: it must be ignored. So "skip hidden" and "read hidden" are both wrong as blanket rules; the header and the laws decide.
- **The same value can be printed twice.** f03 prints every account sum in the summary part *and* again in the detail part (verified: duplicate `account_subtotal` keys). Carry-overs (Übertrag) repeat a running sum. Completeness checks must not double-count.
- **Zero rows are real rows.** SAP layouts print a class with no assets and all zeros (`5100 Anzahlungen`, verified in f05_01). A correct `0` is a +1, not something to drop.
- **Three kinds of value**: *observed* (pointer shows it), *derived* (computed from observed values by a law), *source inconsistency* (printed, but does not reconcile, so we report it as printed and flag it). Our output and flags sheet should carry this tag per value.
- **`check_corpus.py` is not the scorer.** It is the organisers' corpus integrity check (laws, pointer validity, name leakage). It is still useful: its `pdf_checks` / `xlsx_checks` show what "the pointer shows the value" probably means. For text PDFs the printed string must appear in the page text. For xlsx the value must sit at the coordinate.
- **Related documents.** The corpus has a net/gross pair (f01_03 ↔ f02_02) and an SAP trio (f05/f06/f07 01–02, one ledger). ❓ Is each file scored on its own, or is a client hand-over a *bundle* we may cross-check? Default: single-file, with optional cross-doc checks.
- ❓ Is OCR done by a model (e.g. a vision transformer OCR like docTR or TrOCR, as opposed to an LLM) allowed under rule 01? Our working stance: an OCR engine that outputs characters + bboxes is "code". A generative LLM transcribing digits is not.

Things the second analysis could not see, which still stand: the pointer format and coordinate convention, the corpus format mix (~20/72 docs need OCR), the `_intern/profiles` hint at hidden layouts, and the template / scorer being absent from the repo (verified, not just "not in the uploads").

## 6. Solution direction (to brainstorm next)

A layout-agnostic pipeline where **the LLM classifies and code copies**:

1. **Ingest → uniform "token grid"**: xlsx → cells (value, number_format, hidden/outline, coordinate); text PDF → words + bboxes (pdfplumber); scan / outline → render, deskew / auto-rotate, OCR words + bboxes. Everything becomes `{page|sheet, text, bbox|cell}`.
2. **Page / region triage** (LLM, cheap model): schedule page vs. cover letter / unrelated / blank; where the table starts; unit (EUR / TEUR); fiscal year(s).
3. **Column semantics** (LLM on header text only, no numbers): map header bands to canonical fields; detect multi-line record layouts (f03, f05: field = (line-in-block, column)). Output: a *layout spec* (JSON), cached and reused for every page.
4. **Row segmentation** (code + LLM on labels): asset / continuation / heading / subtotal level / carry-over; identity (asset_no, class, account, position).
5. **Deterministic extraction**: code parses each number token (German / EN / trailing minus / parens / TEUR) into cents, keeping its bbox or cell as the pointer. Glued tokens are split by enumerating split points that satisfy the row laws.
6. **Verifier = confidence gate**: per row, run all laws; per group, subtotal ties; cross-year ties; for scans, OCR-confidence. Write a value only if it passes; otherwise try alternative readings (column shift, re-OCR at higher DPI, other parse), else **blank + flag**. Broken client sums are kept as printed and flagged.
7. **Writer**: fill the Arbeitsversion (both tabs) + pointer columns + a findings / flags sheet.

Generalisation guard: no per-family code. Score on the `layout-mutation` docs as a held-out "unseen layout" proxy, and better still, use the generator itself to create new layout variants for testing.

## 7. Questions for the organisers (most important first)

Each question has its reason and our default if it stays unanswered. If time is short, ask **Q1 to Q5**: they change the architecture. The rest change details.

1. **Can we get the empty Arbeitsversion template and the scorer?** The brief says we get both, but neither is in the corpus folder or the repo history.
   *Why:* we can't build the output writer or measure ourselves without them. *Default:* use the `.key.json` schema as the output format and write our own scorer from it.
2. **What exactly do we submit per document?** An `.xlsx` in the template, or JSON / CSV? Where do the pointer and the flag go: extra columns, a separate sheet, or a sidecar file?
   *Why:* it fixes the output contract. *Default:* the template plus a pointer column per value and a flags sheet.
3. **How are our rows matched to the answer key?** For assets, by asset number + sub-number + year? For class rows, by class code, account or name? How is an extra row we output (one that isn't in the key) scored, and how is a key row we miss scored? Is a missing row the same as a blank (0)?
   *Why:* it decides how much effort goes into identity extraction, and whether over-producing rows is dangerous. *Default:* match on `(year, asset_no, sub_no)` and `(kind, year, class/account/position)`. We treat extra rows as risky.
4. **What counts as "the pointer shows the value"?**
   - PDFs: page + bounding box? How much overlap is needed? Is a row box enough, or do you need the exact cell box? Which coordinate system: points with a top-left origin, as in the keys?
   - Scans and rotated pages: coordinates on the image as given, or after we straighten it?
   - Excel: the exact cell coordinate?

   *Why:* a correct value with a bad pointer scores −3. *Default:* page + a value-level bbox in pdfplumber points on the page as given; the exact cell for Excel.
5. **Does OCR by a model break rule 01 ("the model never writes a number")?** Is an OCR model fine (Tesseract, docTR, PaddleOCR)? Is a vision LLM (GPT-4o) reading the digits forbidden, even if code then checks the result?
   *Why:* ~20 of 72 documents have no text layer, so this decides the whole OCR stack. *Default:* OCR engines are allowed; LLMs never transcribe digits.
6. **Are computed values allowed?** Two keys expect values rebuilt from the accounting rules: f05_05 / f06_06, where the last column is cut off at the page edge, and f09_05, where the transfer cell is empty but the key has the implied value. Should we:
   - (a) compute the value with code and flag it,
   - (b) leave it blank and flag it, or
   - (c) report what's printed?

   What pointer is expected for a computed value? *Default:* (a), but only when every other term in the rule was read directly; the pointer goes to the cut-off or empty cell.
7. **How are flagged fields scored?** That means glued numbers, cut-off columns, and subtotals that don't add up. Are they scored normally, or left out? Does writing the flag itself earn anything?
   *Default:* scored normally; a subtotal that doesn't add up is reported as printed plus a flag.
8. **Which rows are scored?** Only asset rows and class rows, or also account, position and grand totals and carry-over lines? On the Anlagengitter tab, if the document lists individual assets, should the class row be the printed class subtotal, or may code add up the assets? If code adds them, what is the pointer?
   *Default:* score everything that is keyed; fill class rows only from printed subtotals.
9. **What will the hidden test set contain?** Which formats (will there be Word files)? About how many documents? Could there be documents that aren't asset schedules at all (trial balances, balance sheets), where the right output is empty? Partial lists, like additions-only or disposals-only lists?
   *Why:* it decides how much we invest in Word input and in recognising non-schedules. *Default:* expect all of these (see assumption 9).
10. **Signs and units:** do we output magnitudes like the keys (positive, transfers signed), or values as printed? For documents in thousands of euros (TEUR), the printed number × 1000 in euros?
    *Default:* magnitudes, and TEUR × 1000 (assumptions 7 and 8).
11. **Is a correct zero scored +1?** Does a blank cell in the document (for example, no additions) count as 0, or as "not applicable"?
    *Default:* +1, so we write zeros explicitly (assumption 11).
12. **Is each file scored on its own, or as a client bundle?** May we check related files against each other (the SAP trio, the net/gross pair)?
    *Default:* each file on its own (assumption 13).
13. **Run conditions:** is there a time or cost limit per document? Do we submit code or outputs? Is internet / API access available when the final test runs?
    *Default:* assumption 14.
