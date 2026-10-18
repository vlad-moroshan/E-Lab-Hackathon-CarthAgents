# JSON evaluator

Data-quality checks for extraction output: one JSON per document in the answer-key format, with the local
evaluator extensions of `carth eval` (null amounts for blanks, optional per-value `pointers`). Files are named
`<doc_id>.pred.json` (as in `out/pred/`), `<doc_id>.json` or `<doc_id>.key.json`.

```sh
# every check, one command; writes PRED_DIR/_eval/summary.md, summary.json and docs/<doc_id>.json
uv run python json_evaluator/run_all.py out/pred [--corpus A3-Hackathon-Corpus] [--out DIR] \
    [--missing-as blank|wrong] [--baseline OLD/_eval/summary.json]

# browser view of one run
uv run python dashboard/dashboard.py out/pred --open

# planted mistakes that every check must catch
uv run python json_evaluator/selftest.py
```

## Checks

| script | needs key | what it checks |
|---|---|---|
| `check_schema.py` | no | meta, row kinds, years, int cents, only `umbuchung` signed, every blank flagged, every value has a pointer, `printed` parses to the value, no duplicate assets |
| `check_laws.py` | no | row laws (cost, depreciation, book values, net layout); names the suspect field whose correction fixes the row |
| `check_totals.py` | no | subtotals = sum of their rows, telling a client sum that does not tie (keep and flag) from a suspected read error; transfers net to 0; year N closing = year N+1 opening |
| `check_pointers.py` | no (source document) | re-reads every value at its pointer: the Excel cell, or the PDF words inside the box |
| `check_completeness.py` | no (source document) | every schedule line of the source (two or more amounts) is in the output or listed in `meta.skipped` |
| `score.py` | yes | +1 correct / 0 blank / −3 wrong; cause of each wrong value (sign, unit scale, column shift, row shift, parse vs read error, pointer only) and its size; flags vs the key's flags; name, date, useful life, method |
| `check_planted.py` | yes | each planted problem handled as its `expected_behaviour` asks |
| `run_all.py` | – | all of the above and the report; exit 1 on schema errors or a score below `--baseline` |
| `selftest.py` | – | 13 planted mistakes, each must be caught |
| `common.py` | – | output format, row laws, amount parser, row matching, PDF word reader |

The first five need no answer key and also run on unseen documents. Each script runs alone too, with one OK/FAIL
line per document: `uv run python json_evaluator/<script>.py PRED_DIR [CORPUS_DIR]`.

## Relation to `carth eval`

`carth eval` is the local stand-in for the leaderboard scorer and matches predictions to key rows by pointer
location. `score.py` matches rows by identity (year, kind, asset number, class, account, position, then pointer)
to explain each wrong value; it reports output rows the key does not have but does not score them, where
`carth eval` charges them −3. Use `carth eval` for the score and this evaluator for diagnosis and quality gates.
Neither is the official scorer.

## Output conventions the checks rely on

- `fields[f] = null` is a blank and needs `flags[f]` (or `flags["*"]`) with a reason.
- Amounts are int cents, magnitudes; only `umbuchung` is signed. An empty cell is `0`, not a blank.
- Pointers: `{page, line, bbox}` or `{sheet, cell, cells: {field: "C8"}}`; a row may add
  `pointers: {field: {page, bbox} | {sheet, cell}}` per value. A PDF value counts as at the right place when its
  box lies on the key row's line.
- Flags the keys use: `glued`, `non_tying` (row-wide, `"*"`), `cut_off`, `transfer_incomplete`. Values flagged
  `cut_off` / `transfer_incomplete` are derived, not read, so the pointer re-read skips them.
- Lines left out on purpose go into `meta.skipped`:
  `[{"page": 3, "reason": "unrelated report"}, {"sheet": "Sheet1", "rows": [68, 82], "reason": "forecast"}]`.
  This property is outside the strict corpus schema, like null amounts and `pointers`.

## Limits

- Scans and PDFs without a text layer cannot be re-read or checked for completeness without OCR; they are counted
  as not verifiable.
- Missing values (neither output nor flagged) score 0 by default; `--missing-as wrong` scores them −3.
- `net_fields` (`bew_ahk`, `bew_wb` in f07) are outside `fields` in the keys and are not scored.
- In `f09_excel_register_05` the key holds the implied transfer on `transfer_incomplete` rows, not the printed one.
