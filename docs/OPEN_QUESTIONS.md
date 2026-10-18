# Open questions

Unspecified organiser contracts and remaining requirements for the [pipeline](CHALLENGE_UNDERSTANDING.md).

## 1. Submission schema and naming

Runtime [extraction.schema.json](../carth/extraction.schema.json) supports per-value evidence, blank reasons, problem flags and unknown source metadata. The original [corpus schema](../carth/eval/corpus.schema.json) remains the strict answer-key contract. Organiser acceptance of the extraction envelope and required submission filenames remains unconfirmed. Do not fabricate family, seed or invented-name metadata for unfamiliar sources.

## 2. Judging and evidence

The supplied integrity checker does not implement the brief's +1/0/−3 truth/completeness score. Local evaluation uses conservative source references, identity and signed net fields, rejects weak/multi evidence and checks full token coverage. It remains heuristic: learned columns and OCR references are not independent source truth. Exact leaderboard invocation, rotated-page convention, overlap/repeated-presentation matching, blank-flag semantics and bounding-box tolerances remain unspecified.

Full-batch `check` and `recall` fail missing outputs/caches; `--partial` requests an explicit partial diagnostic. Checker success does not certify source completeness. Arithmetic and hierarchy verification of runtime extraction still need implementation.

## 3. Source/key contradictions

Clipped fields in f05_05/f06_06 and seven transfer conflicts in f09_05 contradict direct observed-evidence scoring. Local Excel compliance uses the actual source cell and reports the conflict separately. Clipped source characters remain unresolved. Organiser credit and dependency-evidence contracts for derived amounts remain unspecified. Printed values must be preserved; arithmetic is not permission to repair them.

## 4. Workbook conventions

Both JSON and a filled Arbeitsversion XLSX are required. The local writer uses annual sheets within one document workbook, preserving all reporting years in JSON. It does not infer fiscal end dates from year labels. Organiser acceptance of annual sheets, account-level rows in grids and supplemental register column AR for unsplit total depreciation remains unconfirmed. Planned/unplanned or gross/net components cannot be invented.

Template formulas are retained as template calculations, distinct from imported literal values; their caches are not recalculated. Source totals remain literal observations even when inconsistent.

## 5. Runtime coverage and conditions

Automatic section/record/layout discovery, model-reference validation, broad extraction completeness, arithmetic/hierarchy checks and automatic OCR orchestration remain unfinished. The current runner consumes reviewed fingerprinted layout references and explicitly flags missing layouts. It is not a complete unattended hidden-test agent.

API/network availability, runtime/cost limits, supported OCR environments, individual-document versus bundle evaluation, and formats beyond PDF/XLSX remain unspecified. Deskew and fresh CPU/OCR performance measurements are pending. Alternate OCR engines have not been validated. OCR model transcription is permitted, but acceptable generative vision methods remain unspecified; code must retrieve and parse every reported amount.
