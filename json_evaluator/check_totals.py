#!/usr/bin/env python3
"""Totals: do subtotals equal the sum of their rows, do transfers net to zero, does one year carry into the next?
Needs no answer key.

- subtotal / total = sum of the asset rows under it, field by field (TEUR within rounding)
    * all child rows pass their row laws -> the client's sum is off: keep the printed value, it must be flagged
      ('client_non_tying': warn when flagged, error when not; rule 05: flag, never fix)
    * some child rows break their laws   -> more likely a read error in those rows ('read_error_suspected')
- sum of Umbuchung over all asset rows of a year = 0
- multi-year: closing values of year N = opening values of year N+1 for the same row

    python3 "json evaluator/check_totals.py" PRED_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CARRY_FORWARD, TOTAL_KINDS, is_flagged, issue, iter_predictions, kids_of,  # noqa: E402
                    law_residuals, load, numeric, row_label, tolerance)

CHECK = "totals"


def _row_ok(r: dict, unit: str) -> bool:
    return all(abs(d) <= tol for _, _, d, tol in law_residuals(r, unit))


def check(pred: dict) -> list[dict]:
    unit = pred.get("meta", {}).get("unit", "EUR")
    rows = pred.get("rows", [])
    out = []
    for i, r in enumerate(rows):
        if r.get("kind") not in TOTAL_KINDS:
            continue
        kids = kids_of(rows, i)
        if not kids:
            out.append(issue(CHECK, "warn", "total row has no asset rows under it", r))
            continue
        for f, v in (r.get("fields") or {}).items():
            if numeric(r["fields"], f) is None:
                continue
            if any(f in (a.get("fields") or {}) and numeric(a["fields"], f) is None for a in kids):
                continue  # a blank child: cannot tie
            diff = v - sum(numeric(a.get("fields") or {}, f) or 0 for a in kids)
            if abs(diff) <= tolerance(unit, len(kids) + 1):
                continue
            bad_kids = [a for a in kids if not _row_ok(a, unit)]
            if bad_kids:
                out.append(issue(CHECK, "error", f"{f} off by {diff / 100:,.2f} EUR vs {len(kids)} rows; "
                                 f"{len(bad_kids)} child rows break their laws (read error suspected)", r, f,
                                 diff=diff, cause="read_error_suspected",
                                 children=[row_label(a) for a in bad_kids[:5]]))
            else:
                out.append(issue(CHECK, "warn" if is_flagged(r, f) else "error",
                                 f"{f} off by {diff / 100:,.2f} EUR vs {len(kids)} rows (client sum does not tie"
                                 + ("" if is_flagged(r, f) else ", not flagged") + ")", r, f,
                                 diff=diff, cause="client_non_tying"))

    years = sorted({r.get("year") for r in rows})
    for y in years:
        um = [numeric(r.get("fields") or {}, "umbuchung") for r in rows
              if r.get("kind") == "asset" and r.get("year") == y and "umbuchung" in (r.get("fields") or {})]
        if um and None not in um and sum(um) != 0:
            out.append(issue(CHECK, "warn", f"{y}: Umbuchungen over all assets net to {sum(um) / 100:,.2f} EUR, not 0",
                             None, "umbuchung", year=y))

    def ident(r):
        return (r.get("kind"), r.get("asset_no"), r.get("sub_no"), r.get("class"), r.get("account"),
                r.get("position"), r.get("level"), r.get("name") if r.get("kind") == "asset" else None)

    by_year = {y: {} for y in years}
    for r in rows:
        by_year[r.get("year")].setdefault(ident(r), []).append(r)
    for y0, y1 in zip(years, years[1:]):
        if y1 != y0 + 1:
            continue
        for k, rs0 in by_year[y0].items():
            rs1 = by_year[y1].get(k)
            if not rs1 or len(rs0) != 1 or len(rs1) != 1:
                continue
            a, b = rs0[0].get("fields") or {}, rs1[0].get("fields") or {}
            for close, open_ in CARRY_FORWARD.items():
                ca, ob = numeric(a, close), numeric(b, open_)
                if ca is not None and ob is not None and ca != ob:
                    out.append(issue(CHECK, "warn", f"{y0} {close} {ca / 100:,.2f} != {y1} {open_} {ob / 100:,.2f}",
                                     rs1[0], open_, diff=ob - ca))
    return out


def main(pred_dir: str) -> int:
    bad = 0
    for doc_id, path in iter_predictions(Path(pred_dir)):
        res = check(load(path))
        errs = [i for i in res if i["severity"] == "error"]
        bad += bool(errs)
        warns = len(res) - len(errs)
        print(("FAIL " if errs else "OK   ") + doc_id + (f" ({warns} warnings)" if warns else "")
              + (": " + "; ".join(f"{e.get('row', '')} {e['message']}" for e in errs[:3]) if errs else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
