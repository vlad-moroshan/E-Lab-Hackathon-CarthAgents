# Evaluator

Checks the data quality of the pipeline's output JSONs. The output format is the answer-key format
(`A3-Hackathon-Corpus/<family>/<doc_id>.key.json`), one file per document, named `<doc_id>.json`.

```bash
# everything, one command (writes PRED_DIR/_eval/summary.md, summary.json, docs/<doc_id>.json)
.venv/bin/python "json evaluator/run_all.py" PRED_DIR [--corpus A3-Hackathon-Corpus] [--out DIR] \
    [--missing-as blank|wrong] [--baseline OLD_RUN/summary.json]

# prove the evaluator catches planted mistakes
.venv/bin/python "json evaluator/selftest.py"
```

## Scripts

| script | needs key | what it checks |
|---|---|---|
| `check_schema.py` | no | meta, row kinds, years, int cents, only `umbuchung` signed, every blank flagged, every value has a pointer, `printed` parses to the value, no duplicate assets |
| `check_laws.py` | no | row laws (cost, depreciation, book values, net layout); names the **suspect field** whose correction fixes the row |
| `check_totals.py` | no | subtotals = sum of their rows; tells **client non-tying** (keep + flag) from **read error suspected**; transfers net to 0; year N closing = year N+1 opening |
| `check_pointers.py` | no (source doc) | re-reads every value at its pointer: Excel cell, or PDF text inside the box; scans and outline PDFs are counted as not verifiable |
| `check_completeness.py` | no (source doc) | every schedule line in the source (2+ amounts) is in the output or listed in `meta.skipped` |
| `score.py` | yes | +1 correct / 0 blank / −3 wrong; wrong-value cause (sign, unit scale, column shift, row shift, parse vs read error, pointer only) and size; flags vs key flags; name/date/useful life/method |
| `check_planted.py` | yes | each planted problem handled as its `expected_behaviour` asks |
| `run_all.py` | – | runs all of the above, writes the report; exit 1 on schema errors or a score below `--baseline` |
| `selftest.py` | – | 13 planted mistakes, each must be caught |
| `common.py` | – | format, laws, amount parser, row matching |

The first five run on the hidden test set too (no key needed); they are the data-quality gate.
`score.py` and `check_planted.py` run on the 72 sample documents.

Each script also runs alone: `python3 "json evaluator/<script>.py" PRED_DIR [CORPUS_DIR]` (one OK/FAIL line per document).
`check_pointers.py` and `check_completeness.py` need PyMuPDF and openpyxl, so use `.venv/bin/python`.

## Output conventions the checks rely on

- `fields[f] = null` is a blank and needs `flags[f]` (or `flags["*"]`) with a reason, otherwise it is a schema error.
- Amounts are int cents, magnitudes; only `umbuchung` is signed. An empty cell is `0`, not a blank.
- Pointers: `{page, line, bbox}` (row box; optional `boxes: {field: bbox}` per value) or
  `{sheet, cell, cells: {field: "C8"}}`. A PDF pointer counts as right when the value's box lies on the key's line.
- Flags the keys use: `glued`, `non_tying` (row-wide, `"*"`), `cut_off`, `transfer_incomplete`. Values flagged
  `cut_off` / `transfer_incomplete` are derived, not read, so the pointer re-read skips them.
- Lines the pipeline leaves out on purpose go into `meta.skipped`:
  `[{"page": 3, "reason": "unrelated report"}, {"sheet": "Sheet1", "rows": [68, 82], "reason": "forecast"}]`.

## Scoring choices to confirm with the organisers

- Missing values (neither output nor flagged) score 0 by default; `--missing-as wrong` scores them −3.
- Output rows the key does not have are reported, not scored.
- `net_fields` (`bew_ahk`, `bew_wb` in f07) are outside `fields` in the keys and are not scored.
