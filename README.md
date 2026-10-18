# CarthAgents — Zero-Hallucination Audit Agent

**TUM.ai hackathon · 18 October 2026**

Extract German fixed-asset reports into **one schema-based JSON file per document**, with source evidence for every amount. Code parses the figures; models interpret layout. Preserve printed errors, flag uncertainty, and check accuracy and completeness.

```text
Documents → extraction + validation → JSON → optional, separate XLSX conversion
```

The `carth` package currently provides text-PDF/Excel ingestion, schema validation and evaluation tools. The unattended extraction command and optional workbook converter still need implementation.

- [Project guide](docs/CHALLENGE_UNDERSTANDING.md): output contract, pipeline, commands and reporting years.
- [Data and workbook reference](docs/REFERENCE.md): corpus families, accounting fields, template mapping and all 72 samples.
- [Open inconsistencies](docs/OPEN_QUESTIONS.md): schema gaps and unresolved requirements.
- [Challenge materials](challenge/): short brief, detailed brief and Arbeitsversion template.
- [JSON Schema](carth/eval/corpus.schema.json) · [Development corpus](A3-Hackathon-Corpus/).
- [JSON evaluator](json_evaluator/README.md) · [evaluation dashboard](dashboard/README.md): data-quality checks on extraction output.

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
