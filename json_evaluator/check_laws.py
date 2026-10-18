#!/usr/bin/env python3
"""Row laws: does every row add up on its own? Needs no answer key, so it also runs on the hidden test set.

    AHK 31.12.       = AHK 01.01. + Zugang - Abgang + Umbuchung
    kum. AfA 31.12.  = kum. AfA 01.01. + AfA GJ - AfA Abgang - Zuschreibung
    Buchwert 31.12.  = AHK 31.12. - kum. AfA 31.12.
    Buchwert VJ      = AHK 01.01. - kum. AfA 01.01.
    (net layouts)    Buchwert 31.12. = Buchwert VJ + Zugang + Umbuchung - Abgang(BW) - AfA GJ + Zuschreibung

A law is checked only when the row prints all its fields (blanks skip it). For a broken row the check names the
suspect field: the one field whose correction makes every law of the row hold. A broken law on a row the output
flagged is a warning (the pipeline saw it); unflagged it is an error.

    python3 "json evaluator/check_laws.py" PRED_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import is_flagged, issue, iter_predictions, law_residuals, load  # noqa: E402

CHECK = "laws"


def suspects(r: dict, unit: str) -> list[str]:
    """Fields whose single correction would make every law of the row hold."""
    broken = [(t, terms, d) for t, terms, d, tol in law_residuals(r, unit) if abs(d) > tol]
    if not broken:
        return []
    out = []
    t0, terms0, d0 = broken[0]
    for f in {t0, *terms0}:
        if f not in r["fields"] or r["fields"][f] is None:
            continue
        coef = 1 if f == t0 else terms0[f]
        trial = dict(r, fields=dict(r["fields"]))
        trial["fields"][f] = r["fields"][f] - d0 * coef  # value that closes the first broken law
        if trial["fields"][f] >= 0 or f == "umbuchung":
            if all(abs(d) <= tol for _, _, d, tol in law_residuals(trial, unit)):
                out.append(f)
    return sorted(out)


def check(pred: dict) -> list[dict]:
    unit = pred.get("meta", {}).get("unit", "EUR")
    out = []
    for r in pred.get("rows", []):
        for target, terms, diff, tol in law_residuals(r, unit):
            if abs(diff) <= tol:
                continue
            sus = suspects(r, unit)
            sev = "warn" if is_flagged(r) else "error"
            law = f"{target} = " + " ".join(("+ " if s > 0 else "- ") + t for t, s in terms.items()).lstrip("+ ")
            out.append(issue(CHECK, sev, f"{law} off by {diff / 100:,.2f} EUR"
                             + (f"; suspect {', '.join(sus)}" if sus else ""), r, target, diff=diff, suspects=sus))
    return out


def main(pred_dir: str) -> int:
    bad = 0
    for doc_id, path in iter_predictions(Path(pred_dir)):
        res = check(load(path))
        errs = [i for i in res if i["severity"] == "error"]
        bad += bool(errs)
        warns = len(res) - len(errs)
        print(("FAIL " if errs else "OK   ") + doc_id + (f" ({warns} flagged)" if warns else "")
              + (": " + "; ".join(f"{e['row']} {e['message']}" for e in errs[:3]) if errs else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
