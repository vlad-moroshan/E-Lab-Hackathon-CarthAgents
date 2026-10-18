#!/usr/bin/env python3
"""Schema check: is every output JSON well formed, and does every value carry what the scorer needs?

- meta: doc_id, unit (EUR/TEUR), years
- rows: known kind, year in meta.years, fields int cents or null, only umbuchung negative
- every blank (null) has a flag with a reason; every value has a pointer (page+bbox or sheet+cell)
- printed strings parse to the value they claim (unless flagged glued / cut_off)
- no duplicate asset rows; asset rows print the same field set

    python3 "json evaluator/check_schema.py" PRED_DIR
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AMOUNT_FIELDS, DERIVED_FLAGS, ROW_KINDS, SIGNED_FIELDS, issue, iter_predictions, load, parse_amount  # noqa: E402

CHECK = "schema"
_CELL = re.compile(r"^[A-Z]{1,3}[1-9]\d*$")


def _bbox_ok(b) -> bool:
    return (isinstance(b, (list, tuple)) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)
            and b[0] <= b[2] and b[1] <= b[3])


def check(pred: dict) -> list[dict]:
    out = []
    meta = pred.get("meta")
    if not isinstance(meta, dict):
        return [issue(CHECK, "error", "missing meta")]
    for k in ("doc_id", "unit", "years"):
        if k not in meta:
            out.append(issue(CHECK, "error", f"meta.{k} missing"))
    unit = meta.get("unit", "EUR")
    if unit not in ("EUR", "TEUR"):
        out.append(issue(CHECK, "error", f"meta.unit {unit!r} not EUR/TEUR"))
    years = meta.get("years") or []
    rows = pred.get("rows")
    if not isinstance(rows, list) or not rows:
        return out + [issue(CHECK, "error", "no rows")]

    seen = Counter()
    for r in rows:
        kind = r.get("kind")
        if kind not in ROW_KINDS:
            out.append(issue(CHECK, "error", f"unknown kind {kind!r}", r))
        if years and r.get("year") not in years:
            out.append(issue(CHECK, "error", f"year {r.get('year')} not in meta.years {years}", r))
        fields, printed, flags = r.get("fields"), r.get("printed") or {}, r.get("flags") or {}
        if not isinstance(fields, dict) or not fields:
            out.append(issue(CHECK, "error", "row has no fields", r))
            continue
        if kind == "asset" and not (r.get("asset_no") or r.get("name")):
            out.append(issue(CHECK, "warn", "asset row has neither asset_no nor name", r))
        for f in flags:
            if f != "*" and f not in fields:
                out.append(issue(CHECK, "warn", f"flag on field {f!r} the row does not have", r, f))
        p = r.get("pointer") or {}
        is_pdf, is_xlsx = "page" in p, "sheet" in p
        if not (is_pdf or is_xlsx):
            out.append(issue(CHECK, "error", "row has no pointer", r))
        if is_pdf:
            if not isinstance(p.get("page"), int) or p["page"] < 1:
                out.append(issue(CHECK, "error", f"bad page {p.get('page')!r}", r))
            if not _bbox_ok(p.get("bbox")):
                out.append(issue(CHECK, "error", f"bad bbox {p.get('bbox')!r}", r))
            for f, b in (p.get("boxes") or {}).items():
                if not _bbox_ok(b):
                    out.append(issue(CHECK, "error", f"bad box {b!r}", r, f))
        if is_xlsx:
            if not _CELL.match(str(p.get("cell", ""))):
                out.append(issue(CHECK, "warn", f"bad row cell {p.get('cell')!r}", r))
            for f, c in (p.get("cells") or {}).items():
                if not _CELL.match(str(c)):
                    out.append(issue(CHECK, "error", f"bad cell {c!r}", r, f))

        for f, v in fields.items():
            if f not in AMOUNT_FIELDS:
                out.append(issue(CHECK, "warn", f"unknown field {f!r}", r, f))
            if v is None:
                if f not in flags and "*" not in flags:
                    out.append(issue(CHECK, "error", "blank value without a flag", r, f))
                continue
            if isinstance(v, bool) or not isinstance(v, int):
                out.append(issue(CHECK, "error", f"value {v!r} is not int cents", r, f))
                continue
            if v < 0 and f not in SIGNED_FIELDS:
                out.append(issue(CHECK, "error", f"negative {f} ({v}); only umbuchung is signed", r, f))
            if is_xlsx and f not in (p.get("cells") or {}) and v != 0:
                out.append(issue(CHECK, "error", "value has no cell pointer", r, f))
            if f in printed and flags.get(f) not in ("glued", *DERIVED_FLAGS):
                parsed = parse_amount(printed[f], unit)
                if parsed is None:
                    out.append(issue(CHECK, "error", f"printed {printed[f]!r} is not an amount", r, f))
                elif abs(parsed) != abs(v):
                    out.append(issue(CHECK, "error", f"printed {printed[f]!r} parses to {abs(parsed)}, value is {v}",
                                     r, f))
        if kind == "asset" and r.get("asset_no"):
            seen[(r.get("year"), str(r["asset_no"]), str(r.get("sub_no") or ""))] += 1

    for (y, a, s), n in seen.items():
        if n > 1:
            out.append(issue(CHECK, "error", f"asset {a}/{s} appears {n} times in {y}"))
    sets = Counter(tuple(sorted(r["fields"])) for r in rows if r.get("kind") == "asset" and r.get("fields"))
    if len(sets) > 1:
        common_set = set(sets.most_common(1)[0][0])
        for r in rows:
            if r.get("kind") == "asset" and r.get("fields") and set(r["fields"]) < common_set:
                out.append(issue(CHECK, "warn", f"missing fields {sorted(common_set - set(r['fields']))}", r))
    return out


def main(pred_dir: str) -> int:
    bad = 0
    for doc_id, path in iter_predictions(Path(pred_dir)):
        errs = [i for i in check(load(path)) if i["severity"] == "error"]
        bad += bool(errs)
        print(("FAIL " if errs else "OK   ") + doc_id + (": " + "; ".join(
            f"{e.get('row', '')} {e.get('field', '')} {e['message']}".strip() for e in errs[:3]) if errs else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
