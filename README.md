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

From the repository root:

```sh
uv run carth validate-corpus
uv run python -m unittest discover -s tests -v
```

## Review frontend

The read-only React + TypeScript demo lives in [`frontend/`](frontend/README.md). It loads key-style JSON directly, displays source PDF evidence and findings, and downloads an attached backend-generated workbook.

```sh
cd frontend
npm ci
npm run dev
```

Use Node 22.13+ and open the URL printed by Vite. The bundled sample is explicitly labelled; extraction and workbook generation remain separate backend steps.
