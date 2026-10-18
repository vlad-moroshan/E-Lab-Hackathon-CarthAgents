# CarthAgents review demo

A read-only React + TypeScript review workspace for the TUM.ai fixed-asset challenge. Runs locally with Vite. The backend remains responsible for extraction and generating the Arbeitsversion workbook.

## Start

Use Node 22.13+ (or a newer supported Node version).

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. `npm run build` creates `dist/`; `npm test` checks the JSON adapter's key behaviours.

## Demo flow

1. The app opens the explicitly labelled synthetic `f00_demo_04` corpus sample.
2. Search for `210004`, then select its Additions amount to inspect `19.425,96` and the PDF row highlight.
3. Select **Needs review** to inspect sample flags. These come from the fixture, not a live extraction.
4. **Load results** accepts a backend JSON file. Attach its matching PDF afterwards.
5. Attach the backend-generated `.xlsx` file. The header then offers **Download Excel**. The app does not generate or verify this workbook; select the file from the same backend run.

Loading a new JSON clears earlier PDF/Excel attachments to avoid stale downloads. No edits, server upload, login, or extraction endpoint are included. Reloading returns to the sample. Files stay in browser memory and are not persisted. The stylesheet loads Google Fonts; system fonts are the fallback when offline.

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
- `src/App.tsx`: review table, direct file loading, findings, and workbook attachment/download.
- `src/PdfViewer.tsx`: local PDF.js rendering and honest row/field highlights.
- `src/style.css`: responsive CarthAgents-inspired visual styling.
- `public/demo`: unmodified synthetic PDF and key JSON from the supplied corpus.

Future API integration can replace `loadJson` with a fetch and feed the response through `parseResult`. Keep the PDF and workbook URLs tied to the same result version. There is deliberately no Excel-export mapping implementation here: the backend owns the template export, including the distinction between annual total depreciation and planned depreciation.

## Demo scope

The bundled f00 example contains individual assets. In other families, `kind: asset` can mean a class/account/position leaf rather than an individual asset. The current Assets label is intended for the chosen demo, not a general granularity classifier. Additional `net_fields` are retained in the loaded row but are not displayed in the amount table. See the [project guide](../docs/CHALLENGE_UNDERSTANDING.md) before expanding to those document families.
