# Pitch diagrams

Editable Mermaid sources for the three-slide [Marp pitch](../architecture-pitch.md). The checked-in SVGs are generated from `.mmd` sources with `theme.json`. Marp uses those SVG images directly, so diagrams render in both browser previews and slide exports without a browser-side Mermaid plugin.

```sh
npx --yes @mermaid-js/mermaid-cli@12 -i docs/pitch-diagrams/flow.mmd -o docs/pitch-diagrams/flow.svg -c docs/pitch-diagrams/theme.json -b transparent
# Repeat for evidence.mmd and mapping.mmd.
npx --yes @marp-team/marp-cli docs/architecture-pitch.md --allow-local-files --pdf -o docs/architecture-pitch.pdf
```

The illustrative example shows selected evidence, plan and output fields from main, not a complete payload. Native Excel evidence uses document-local token IDs such as `t3`, stored cell values and sheet/cell coordinates. The LLM sees masked amounts and returns section rules; it does not supply the financial figures. Evidence IDs are stable for an unchanged source and reader configuration. The mapping plan identifies row patterns, reporting year and semantic amount fields; deterministic code applies those rules across the table and retrieves each source amount. No live model-evaluation claim is made.

Open the [PDF](../architecture-pitch.pdf) to present, or edit the [Markdown](../architecture-pitch.md) and Mermaid sources to revise it.
