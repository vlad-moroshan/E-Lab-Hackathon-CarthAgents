# Evaluation dashboard

Browser view of one evaluation run, one method's output folder. To compare methods, build one dashboard per folder.

```sh
uv run python json_evaluator/run_all.py out/pred        # writes out/pred/_eval/
uv run python dashboard/dashboard.py out/pred --open    # writes out/pred/_eval/dashboard.html
```

The page is one self-contained HTML file and works offline. The name shown is the folder name (`--label` changes
it, `-o` the output file). Rebuild it after every evaluation run.

- **Overview**: score, wrong values, flagged blanks, precision, pointer re-read, lines not in the output; values
  that did not score +1; score by format (scan, PDF without text layer, text PDF, Excel), layout family and
  variant; causes and size of wrong values; outcome per field; flags vs the key; checks without a key; planted
  problems.
- **Documents**: every document of the run, filterable and sortable. A document's page lists its wrong values
  (output vs key, printed text, cause), check findings and planted problems.

`dashboard.py` reads the `_eval` folder and embeds the data into `dashboard_template.html`.
