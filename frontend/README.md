# 3.5 CarthAsians review demo

A read-only React + TypeScript review workspace for the TUM.ai fixed-asset challenge. Runs locally with Vite. The backend remains responsible for extraction and generating the Arbeitsversion workbook.

## Start

Use Node 22.13+ (or a newer supported Node version).

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. `npm run build` creates `dist/`; `npm test` checks the JSON adapter's key behaviours.

## Source-first workflow

1. Choose a source PDF or Excel (.xlsx) file, up to 50 MB.
2. **Process document** sends the file to the configured backend and opens its returned JSON in the review workspace. The source stays attached automatically.
3. Select a value to see its original text and PDF region or Excel cell reference. Excel source preview is not implemented.
4. **Download Arbeitsversion** downloads the populated `.xlsx` output for the current result. It stays disabled with an availability message until a workbook is supplied. The frontend does not generate or verify that workbook.

The local bridge returns the generated Arbeitsversion with the extraction result, enabling download automatically. For offline demo setup, the result filename in the footer still opens developer attachments.

Until the backend endpoint is available, real-file processing is disabled. Choose a **prepared PDF or Excel sample**, then **Review sample**, to explore the flow using its supplied answer key. These are explicitly labelled sample results, not extraction runs. Arbitrary uploads never receive a canned sample answer.

Under **Development tools**, select a source document and load its matching JSON. This preserves the selected source and allows backend integration without an HTTP endpoint. The result is labelled imported. **New document** begins another upload; **Back to current review** preserves the existing review until a replacement result succeeds.

## Processing endpoint setup

From the repository root, start the local backend:

```sh
uv sync
uv run python -m carth.server --specs out/layouts
```

Copy `.env.example` to `.env.local` in `frontend`, then start/restart Vite. The endpoint is `http://127.0.0.1:8000/api/process`. The bridge binds only to localhost and allows frontend origins on port 5173. Use `--origin` to add a different local frontend origin.

**Extraction still requires a reviewed layout** named `<source-stem>.layout.json` in the specs folder, with a matching SHA-256. Automatic layout discovery and OCR are not invoked by this bridge. Missing layouts return a visible error, never a canned result or blank workbook presented as success. The integration point for the layout detection team is `process_file` in `carth/server.py`, between ingestion and `extract`.

- Request: `POST multipart/form-data`, one `file` field (PDF/XLSX, up to 50 MB).
- Response: `{result: <runtime extraction JSON>, workbook: {name: "…-Arbeitsversion.xlsx", base64: "…"}}`.
- Runtime JSON is `{version:1, document, rows, values, flags}`. The frontend adapter retains per-field pointers, flags, nulls, raw trace strings and units. All backend amount fields are available under **All amounts**.
- Excel bytes come from `write_outputs`, not a frontend reconstruction. Files stay in browser memory; temporary server files are removed after each response. Cancellation stops the browser request, but may not stop server processing.
- `GET /api/health` reports bridge availability and the layout requirement.
- This synchronous local demo bridge is not a production service; no credentials, job queue or persistence are included.

`src/processing.ts` also accepts direct legacy key-style responses for compatibility. Direct runtime JSON imports work through `parseResult`; offline imports do not include an Excel file automatically.

No edits, login, or automatic extraction are included in prepared samples. Reloading returns to the upload screen. Loaded files are kept in browser memory; processing sends the selected file to the configured endpoint. The stylesheet loads Google Fonts with system-font fallbacks.

## Backend contract

The runtime adapter displays `trace.raw` as **Source value** because Excel traces may contain numeric cell text rather than formatted display strings. PDF trace strings retain the observed source text.

The existing corpus shape is also accepted: `{ meta, rows }`. This is a UI adapter, not the repository’s strict JSON Schema validator. The UI accepts the agreed `null` and `provenance` extensions, which the current [strict schema](../carth/eval/corpus.schema.json) does not allow; see [open questions](../docs/OPEN_QUESTIONS.md). `planted` is deliberately discarded. `rows[].flags` is displayed as sample findings for the bundled fixture and as backend-reported findings for a loaded result. Never populate flags from answer-key knowledge in a real extraction run.

- `meta`: company, doc_id, doc_type, period_end, years, format, unit.
- Each row: kind, year, asset_no, sub_no, class, account, position, name.
- `fields`: amount field names mapped to integer EUR cents or `null`. Zero remains zero; null means unresolved. Absent fields display a dash without an unresolved count.
- `printed`: field names mapped to original strings. Empty string explicitly means a blank printed cell.
- `pointer`: PDF `{ page, bbox: [x0, top, x1, bottom] }`, with one-based pages and coordinates in PDF points from the top-left. The corpus generally supplies a row region. Optional `field_bboxes` maps field names to more precise regions. Excel `{ sheet, cell, cells: { field: "D8" } }` displays a reference; Excel source preview is not implemented.
- `flags`: field names or `"*"` (whole row) mapped to reason strings.
- Optional agreed extension `provenance`: field names mapped to `{ type: "extracted" | "calculated", formula?: string, inputs?: string[] }`. Missing metadata is not presented as verified extraction. Calculated values are labelled explicitly.

Example unresolved and calculated metadata (illustrative, not a measured result):

```json
{
  "meta": { "company": "Demo company", "period_end": "2025-12-31" },
  "rows": [{
    "kind": "asset", "year": 2025, "asset_no": "001", "name": "Machine",
    "fields": { "ahk_open": 10000, "zugang": 0, "abgang": null, "bw_close": 8000 },
    "printed": { "ahk_open": "100,00", "zugang": "" },
    "pointer": { "page": 1, "bbox": [30, 100, 500, 115] },
    "flags": { "abgang": "The source amount could not be read reliably." },
    "provenance": { "bw_close": { "type": "calculated", "formula": "closing cost - accumulated depreciation", "inputs": ["ahk_close", "kum_afa_close"] } }
  }]
}
```

The review table and result amount display integer EUR cents with grouping separators (for example, `1.942.596` cents). “As printed” preserves the original source string. The populated Arbeitsversion remains a separate backend export with its template-defined units.

Amounts in `fields` are always EUR cents even when the source uses TEUR. The backend must perform any justified unit/sign normalisation and preserve the original `printed` representation. A source pointer does not prove accuracy. The app reports supplied values, not an accuracy score.

## Implementation

- `src/model.ts`: input adapter, amount formatting, row identities, evidence selection, and field definitions.
- `src/App.tsx`: review table, findings, source attachment, and workbook download.
- `src/SourceIntake.tsx`: source upload, prepared samples, processing/cancellation, and developer JSON import.
- `src/processing.ts`: source validation and configurable HTTP adapter.
- `src/PdfViewer.tsx`: local PDF.js rendering and honest row/field highlights.
- `src/style.css`: responsive CarthAgents-inspired visual styling.
- `public/demo`: unmodified synthetic PDF and key JSON from the supplied corpus.

Configure the processing endpoint when available; it already feeds the returned JSON through `parseResult`. Keep the PDF and workbook URLs tied to the same result version. There is deliberately no Excel-export mapping implementation here: the backend owns the template export, including the distinction between annual total depreciation and planned depreciation.

## Demo scope

The bundled f00 example contains individual assets. In other families, `kind: asset` can mean a class/account/position leaf rather than an individual asset. The current Assets label is intended for the chosen demo, not a general granularity classifier. Legacy key `net_fields` are retained but not displayed; runtime `net:bew_ahk` and `net:bew_wb` values appear under All amounts. See the [project guide](../docs/CHALLENGE_UNDERSTANDING.md) before expanding to those document families.
