# CarthAgents review demo

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

Automatic workbook delivery awaits the backend contract. For demo setup only, open the result filename in the review footer and load the populated backend output under **Development tools**. Select the workbook from the same run; never use the blank template or source workbook as the output. Loading a new result clears the previous workbook.

Until the backend endpoint is available, real-file processing is disabled. Choose a **prepared PDF or Excel sample**, then **Review sample**, to explore the flow using its supplied answer key. These are explicitly labelled sample results, not extraction runs. Arbitrary uploads never receive a canned sample answer.

Under **Development tools**, select a source document and load its matching JSON. This preserves the selected source and allows backend integration without an HTTP endpoint. The result is labelled imported. **New document** begins another upload; **Back to current review** preserves the existing review until a replacement result succeeds.

## Processing endpoint setup

Copy `.env.example` to `.env.local`, set `VITE_PROCESS_ENDPOINT` to the endpoint provided by the backend team, and restart Vite. For example, `http://localhost:8000/api/process` is a proposed URL, not an existing service. Vite exposes this setting to the browser, so never put secrets in it.

The proposed minimal contract is:

- Request: `POST` with `multipart/form-data`, one field named `file` containing the original PDF/XLSX. The browser sets the multipart boundary.
- Response: HTTP 200 with the key-style JSON object `{ "meta": ..., "rows": [...] }` directly, without an envelope.
- A cross-origin backend must allow the frontend origin (normally `http://127.0.0.1:5173`). No credentials or API keys are sent by this adapter.
- The frontend reports failures, supports retry, and can cancel its request. Cancelling in the browser does not guarantee cancellation of server work.
- This initial adapter expects one completed response. Job IDs, polling, streamed progress, and automatic workbook URLs can be added when the backend defines them.

The request adapter is `src/processing.ts`. The backend endpoint has not been implemented in this frontend change.

No edits, login, or automatic extraction are included in prepared samples. Reloading returns to the upload screen. Loaded files are kept in browser memory; processing sends the selected file to the configured endpoint. The stylesheet loads Google Fonts with system-font fallbacks.

## Backend contract

The existing corpus shape is accepted: `{ meta, rows }`. This is a UI adapter, not the repository’s strict JSON Schema validator. The UI accepts the agreed `null` and `provenance` extensions, which the current [strict schema](../carth/eval/corpus.schema.json) does not allow; see [open questions](../docs/OPEN_QUESTIONS.md). `planted` is deliberately discarded. `rows[].flags` is displayed as sample findings for the bundled fixture and as backend-reported findings for a loaded result. Never populate flags from answer-key knowledge in a real extraction run.

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

The bundled f00 example contains individual assets. In other families, `kind: asset` can mean a class/account/position leaf rather than an individual asset. The current Assets label is intended for the chosen demo, not a general granularity classifier. Additional `net_fields` are retained in the loaded row but are not displayed in the amount table. See the [project guide](../docs/CHALLENGE_UNDERSTANDING.md) before expanding to those document families.
