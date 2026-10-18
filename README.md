# CarthAgents — Zero-Hallucination Audit Agent

**TUM.ai hackathon · 18 October 2026**

Extract German fixed-asset reports into **per-value JSON and a filled Arbeitsversion XLSX per document**, with source evidence for every amount. Code parses the figures; models interpret layout. Preserve printed errors, flag uncertainty, and check accuracy and completeness.

```text
Documents → extraction + validation → per-value JSON → Arbeitsversion XLSX
```

The `carth` package provides ingestion, OCR, local evaluation and a validated JSON/workbook writer. `carth run INPUT OUT --specs LAYOUTS` parses source references from reviewed layout specs. Automatic layout discovery remains unfinished; missing specs produce flagged outputs and a nonzero exit.

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
