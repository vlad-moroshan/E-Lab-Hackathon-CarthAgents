# CarthAgents — Zero-Hallucination Audit Agent

**TUM.ai hackathon · 18 October 2026**

Extract German fixed-asset reports into **per-value JSON and a filled Arbeitsversion XLSX per document**, with source evidence for every amount. Code parses the figures; models interpret layout. Preserve printed errors, flag uncertainty, and check accuracy and completeness.

```text
Documents → extraction + validation → per-value JSON → Arbeitsversion XLSX
```

## Run the agent (one command, unattended)

```sh
uv sync                                   # Python ≥ 3.11; installs pdfplumber, openpyxl, docTR/torch (CPU OCR), openai
echo 'OPENAI_API_KEY=sk-…' > .env         # layout interpretation (default model gpt-6-astra; override with CARTH_MODEL)
uv run carth run INPUT_DIR OUT_DIR        # every .pdf / .xlsx under INPUT_DIR
```

Per document `OUT_DIR/<id>.json` (one record per value: value in cents, row, field, pointer = page + box or sheet + cell,
flags / blank reason, conversion trace) and `OUT_DIR/<id>.xlsx` (copy of the Arbeitsversion template, filled).
`_batch.json` / `_failures.json` summarise the run; the exit code is 1 if any document failed or has blanks.

Pipeline (no GPU, no answer keys at runtime):
1. **Ingest**: PDF text layer words with boxes (all text directions), Excel cells (hidden rows, formulas, caches);
   pages without a text layer are OCRed live with docTR on CPU (Paddle orientation model if installed; otherwise each
   page is read upright and turned 180° and the better reading wins).
2. **Layout** (`carth/layout`): lines, page deskew / alignment, amount columns, record hints. Geometry only.
3. **Layout spec** (`carth/spec.py`): an OpenAI model reads the lines with every amount masked and returns structure
   only — sections, columns → fields, record shape, row roles, identity patterns. It never returns a number.
4. **Resolve** (`carth/resolve.py`): applies the spec to every line: records, roles, identities, token references.
5. **Output** (`carth/output.py`): code parses each referenced token / cell into cents, writes JSON + workbook.

Local results on the 72-document sample (lenient identity: printed codes only): ~25,900 values right, ~1,300 wrong,
~300 extra; amounts copied from tokens differ from the key in < 1 % of written values. Known gaps: blank zeros in PDF
columns stay blank (no evidence box yet), sideways scanned pages need the Paddle orientation model, subtotal-kind
conventions. Details: `docs/IMPLEMENTATION.md`, open points: `docs/OPEN_QUESTIONS.md`.

`carth run INPUT OUT --specs LAYOUTS` instead uses reviewed `<id>.layout.json` references (no model call).

- [Project guide](docs/CHALLENGE_UNDERSTANDING.md): output contract, pipeline, commands and reporting years.
- [Data and workbook reference](docs/REFERENCE.md): corpus families, accounting fields, template mapping and all 72 samples.
- [Open inconsistencies](docs/OPEN_QUESTIONS.md): schema gaps and unresolved requirements.
- [Challenge materials](challenge/): short brief, detailed brief and Arbeitsversion template.
- [Extraction schema](carth/extraction.schema.json) · [Corpus fixture schema](carth/eval/corpus.schema.json) · [Development corpus](A3-Hackathon-Corpus/).

From the repository root:

```sh
uv run carth validate-corpus
uv run python -m unittest discover -s tests -v
```

## Review frontend

The read-only React + TypeScript demo lives in [`frontend/`](frontend/README.md). It starts with a PDF/XLSX upload, processes it through a configurable backend endpoint, and displays returned JSON with source evidence. Prepared samples and matching-JSON import work before the endpoint is available.

```sh
cd frontend
npm ci
npm run dev
```

Use Node 22.13+ and open the URL printed by Vite. The bundled sample is explicitly labelled; extraction and workbook generation remain separate backend steps.

Local frontend/backend integration: run `uv run python -m carth.server --specs out/layouts`, then configure the frontend with its `.env.example`. See [frontend setup](frontend/README.md). A matching reviewed layout is still required until automatic layout detection is connected.
