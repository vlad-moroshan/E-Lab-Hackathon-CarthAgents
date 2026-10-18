# CarthAgents — Zero-Hallucination Audit Agent

**Five-hour TUM.ai hackathon · 18 October 2026**

Build an agent that reads German fixed-asset reports and fills a standard audit workbook, with **every financial value traced back to its source**. The challenge is reliable extraction across unfamiliar layouts, followed by accuracy and completeness checks.

This repo contains the supplied challenge materials, synthetic data and the `carth` Python package. The package provides PDF text ingestion, a local evaluation scorer/oracle and corpus-schema validation. A complete extraction agent and submission command are still to be built.

## The task

```text
Input document → extract text/cells/OCR → interpret layout → parse values in code
               → validate → filled Arbeitsversion.xlsx + evidence.json
```

- Submit code with **one command that processes a folder unattended**.
- Produce one filled Excel workbook and one JSON evidence file per input document.
- Put individual assets in the asset register and summary information in the appropriate grid.
- For every amount, retain the row, field and **PDF page + bounding box** or **Excel sheet + cell**.
- Models may interpret the layout; **code must retrieve and parse the figures**.
- Preserve wrong printed sums and flag them. Leave uncertain values blank with a reason.

**Scoring:** correct value **+1**, flagged blank **0**, wrong value **−3**. A pointer that does not support its value also makes that value wrong. The hidden test uses unseen layouts.

## What is provided?

| Location | Contents | Why it matters |
| --- | --- | --- |
| [downloads/](downloads/) | Two-page challenge PDF and `Arbeitsversion-merged-layout-20.xlsx` | Requirements and output template. **Git-ignored:** teammates need these files separately. |
| [Challenge 1 - CarthAgents.pdf](<Challenge 1 - CarthAgents.pdf>) | Tracked one-page challenge brief | Challenge copy available in a fresh clone. |
| [A3-Hackathon-Corpus/](A3-Hackathon-Corpus/) | **72 documents + 72 JSON answer keys** in ten families | Development fixtures with known values and planted problems. |
| [_generator/](A3-Hackathon-Corpus/_generator/) | Synthetic data generator, renderers and fixture checks | Explains how layouts and problems were constructed. |
| [_intern/profiles/](A3-Hackathon-Corpus/_intern/profiles/) | **26 Markdown descriptions** of reference layouts | Context for the layout variations; the original client files are not included. |
| [carth/](carth/) | CLI, PDF ingestion and local evaluation tools | Python package configured by `pyproject.toml` and `uv.lock`. |
| [carth/eval/](carth/eval/) | [Corpus JSON Schema](carth/eval/corpus.schema.json), validator and scorer | The schema validates every answer key; the scorer is a local stand-in for the official one. |
| [docs/CHALLENGE_UNDERSTANDING.md](docs/CHALLENGE_UNDERSTANDING.md) | Colleague's task analysis and design assumptions | Additional team context; assumptions still need organizer confirmation. |
| [AGENTS.md](AGENTS.md) | Detailed task, schema, folder/file reference and complete sample inventory | The working reference for implementation and agent handoffs. |

The corpus contains **18 Excel files and 54 PDFs**: 34 text PDFs, 10 scans and 10 PDFs with outlined text. Its keys describe **4,002 rows and 36,081 standard amount fields**, plus 306 net-movement fields. There are 39 clean-content samples, 24 problem samples and nine layout mutations.

## The ten data families

| Folder | Documents | What it represents | Main difference |
| --- | ---: | --- | --- |
| [f00_demo](A3-Hackathon-Corpus/f00_demo/) | 4 | Simple asset roll-forward with class sums | Same client in Excel, text PDF, scan and a problem version; start here. |
| [f01_net_spiegel](A3-Hackathon-Corpus/f01_net_spiegel/) | 8 | Net roll-forward by account | Starts from book value; no individual assets or full gross cost history. |
| [f02_asset_spiegel](A3-Hackathon-Corpus/f02_asset_spiegel/) | 7 | Gross roll-forward by asset | Asset IDs, dates, useful life, depreciation and hierarchical sums. |
| [f03_block_spiegel](A3-Hackathon-Corpus/f03_block_spiegel/) | 7 | Account summary followed by asset detail | Each record spans cost, depreciation and book-value lines. |
| [f04_verzeichnis](A3-Hackathon-Corpus/f04_verzeichnis/) | 8 | Asset register with closing cost and book value | Only two amount fields per row; boxed or gridless portrait layouts. |
| [f05_sap_class_gitter](A3-Hackathon-Corpus/f05_sap_class_gitter/) | 8 | SAP-style class history grid | Four-line blocks and star-prefixed subtotal levels. |
| [f06_sap_asset_gitter](A3-Hackathon-Corpus/f06_sap_asset_gitter/) | 7 | SAP-style asset history grid | Sideways pages, group headers, class sums and truncated descriptions. |
| [f07_sap_class_summary](A3-Hackathon-Corpus/f07_sap_class_summary/) | 7 | SAP class depreciation summary | Net movements instead of separate additions/disposals; no individual assets. |
| [f08_excel_spiegel_2y](A3-Hackathon-Corpus/f08_excel_spiegel_2y/) | 8 | Handmade roll-forward by balance-sheet position | Two years, shifted tabs, formulas, merged headings and stale/hidden data. |
| [f09_excel_register](A3-Hackathon-Corpus/f09_excel_register/) | 8 | Excel asset register with class summary | Collapsed asset rows, repeated totals, text numbers and auditor checks. |

Some files share actual data: **f01_03 ↔ f02_02**, and **01/02 in f05, f06 and f07**. Most other similarly formatted files represent different synthetic clients. The detailed guide lists the exact document IDs and relationships.

## How the formats relate

**Anlagenspiegel** means an asset roll-forward; **Anlagengitter** is a history grid, often from SAP; **Anlagenverzeichnis** is the individual-asset register. They share cost, depreciation and book-value concepts, but differ in detail, hierarchy and which fields are available. Summary data cannot recover missing individual assets or a missing gross movement breakdown.

Native Excel provides cells, types and formulas. Text PDFs provide positioned characters. **Scans and crisp outline PDFs both need OCR**: sharp-looking letters may still have no selectable text.

Common traps include German `1.234,56` numbers, trailing minus signs, EUR versus thousand-EUR units, blank zeros, wrapped/glued text, repeated totals, non-calendar financial years, multiple years, hidden rows and unrelated pages/tables. The agent must preserve those distinctions.

## The output workbook

The supplied Arbeitsversion is a **27-tab audit template**, broader than the challenge's shorthand description:

- Core: `Anlagenverzeichnis`, `Gitter nach Anlagenklasse`, `Gitter nach Bilanzposition`.
- Supporting work: additions, disposals, documents/items, expense accounts, trial balance, balance sheet, income statement and open questions.
- Schema/support: ten `Feldkatalog …` tabs, lists and merge notes.

The field catalogs specify stable field IDs, types, origins and rules. Workbook amounts are **EUR**; answer-key amounts are **integer cents**. The detailed guide maps the core fields to actual columns.

## Validate the JSON contract

[carth/eval/corpus.schema.json](carth/eval/corpus.schema.json) defines the shared `meta` / `rows` / `planted` answer-key format using JSON Schema Draft 2020-12. It covers family-specific metadata, both pointer types and all planted-problem variants. All **72 keys pass**. It describes development answer keys; the brief's final per-value submission JSON is still unconfirmed.

```sh
uv run carth validate-corpus
uv run python -m unittest discover -s tests -v
```

The validator also checks matching amount/printed keys, row years, field references, bounding-box ordering and document IDs. This checks the JSON contract; it does not verify financial accuracy or that source pointers show the claimed values.

## Resolve early

- The brief promises an official scorer and output schema. **The official scorer and JSON submission schema are still missing.** `carth eval` provides a local stand-in; the generator checker validates fixtures.
- The template has two named grid tabs, not a tab literally called `Anlagengitter`.
- A few keys expect reconstructed clipped amounts or an implied missing transfer, which conflicts with the brief's strict “as printed” evidence rule. Keep observed and derived values distinct and confirm scoring treatment.
- Multi-year output conventions need confirmation; never silently discard a year.

## A practical five-hour focus

1. Confirm the output contract and get **f00 → XLSX + JSON** working through one command.
2. Add native Excel and text-PDF extraction, with deterministic number parsing and evidence pointers.
3. Generalize row/column interpretation across summary, detail and multi-line layouts.
4. Add OCR/orientation handling and conservative abstention.
5. Check arithmetic, missing rows/values and provenance; test held-out families, then package a reproducible run.

Keep the supplied data unchanged. Use answer keys only for evaluation. Prioritize a reliable batch pipeline before a polished interface or the full audit workflow.
