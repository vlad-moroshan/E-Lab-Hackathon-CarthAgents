#!/usr/bin/env python3
"""Planted problems: did the output handle each problem the key plants the way its `expected_behaviour` asks?

One PASS / FAIL per planted entry:
    glued_numbers, non_tying_subtotal, column_cut_off, transfer_breaks_cost_law
                       the affected values are correct, and the row carries a flag
    teur_rounding      meta.unit is TEUR and every value is correct
    multi_year         meta.years matches and every year is scored on its own
    header_only_on_first_page   values on pages 2+ are correct
    noise_page_cover / noise_page_unrelated   no output row points to the noise page
    wrapped_description  the row's name is joined, and no output row sits on the continuation line
    unrelated_table    no output row points into the table's range
    numbers_as_text, hidden_column   the listed fields are correct
    carry_over         no carry-over line is counted as an asset
Every other type: the document scores without a wrong value.

    python3 "json evaluator/check_planted.py" PRED_DIR [CORPUS_DIR]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DEFAULT_CORPUS, Corpus, iter_predictions, load, match_rows, overlap_ratio  # noqa: E402
from score import pointer_ok  # noqa: E402


def _outcomes(key, pred, pairs, want=lambda k, f: True):
    """(correct, total) over key values selected by want(row, field)."""
    good = tot = 0
    for ki, pi in pairs:
        k = key["rows"][ki]
        p = pred["rows"][pi] if pi is not None else None
        for f, kv in (k.get("fields") or {}).items():
            if not want(k, f):
                continue
            tot += 1
            if p is not None and (p.get("fields") or {}).get(f) == kv and pointer_ok(k, p, f):
                good += 1
    return good, tot


def _wrong(key, pred, pairs, want=lambda k, f: True):
    n = 0
    for ki, pi in pairs:
        k = key["rows"][ki]
        p = pred["rows"][pi] if pi is not None else None
        if p is None:
            continue
        for f, kv in (k.get("fields") or {}).items():
            pv = (p.get("fields") or {}).get(f)
            if want(k, f) and pv is not None and (pv != kv or not pointer_ok(k, p, f)):
                n += 1
    return n


def _same_place(a: dict, b: dict) -> bool:
    if "sheet" in a:
        return a.get("sheet") == b.get("sheet") and a.get("cell") == b.get("cell")
    return a.get("page") == b.get("page") and (a.get("line") == b.get("line")
                                               or overlap_ratio(b.get("bbox"), a.get("bbox")) > 0.5)


def evaluate(pred: dict, key: dict) -> list[dict]:
    pairs, _ = match_rows(key["rows"], pred.get("rows", []))
    k2p = dict(pairs)
    res = []
    for pl in key.get("planted", []):
        t, where = pl["type"], pl.get("where", [])
        ok, detail = True, ""
        if t in ("glued_numbers", "non_tying_subtotal", "column_cut_off", "transfer_breaks_cost_law"):
            hits = 0
            for ki, k in enumerate(key["rows"]):
                if not k.get("flags"):
                    continue
                p = pred["rows"][k2p[ki]] if k2p.get(ki) is not None else None
                fl = set(k["flags"]) - {"*"} or set(k.get("fields", {}))
                correct = p is not None and all(
                    (p.get("fields") or {}).get(f) in (k["fields"][f], None) and
                    ((p.get("fields") or {}).get(f) is None or pointer_ok(k, p, f)) for f in fl if f in k["fields"])
                flagged = p is not None and bool(p.get("flags"))
                reason = {"glued_numbers": "glued", "non_tying_subtotal": "non_tying", "column_cut_off": "cut_off",
                          "transfer_breaks_cost_law": "transfer_incomplete"}[t]
                if reason not in k["flags"].values():
                    continue
                hits += 1
                if not (correct and flagged):
                    ok = False
                    detail += f"{k.get('kind')} {k.get('asset_no') or k.get('class') or ''}: " + \
                              ("not flagged; " if not flagged else "") + ("value wrong; " if not correct else "")
            detail = detail or f"{hits} affected rows handled"
        elif t == "teur_rounding":
            g, n = _outcomes(key, pred, pairs)
            ok = pred.get("meta", {}).get("unit") == "TEUR" and g == n
            detail = f"unit {pred.get('meta', {}).get('unit')}, {g}/{n} correct"
        elif t == "multi_year":
            yrs = where[0].get("years", []) if where else key["meta"]["years"]
            per = {y: _outcomes(key, pred, pairs, lambda k, f, y=y: k.get("year") == y) for y in yrs}
            ok = sorted(pred.get("meta", {}).get("years") or []) == sorted(yrs) and all(g == n for g, n in per.values())
            detail = ", ".join(f"{y}: {g}/{n}" for y, (g, n) in per.items())
        elif t == "header_only_on_first_page":
            g, n = _outcomes(key, pred, pairs, lambda k, f: (k.get("pointer") or {}).get("page", 1) >= 2)
            ok, detail = g == n, f"pages 2+: {g}/{n} correct"
        elif t.startswith("noise_page"):
            pages = {w["row"]["page"] for w in where if "row" in w}
            bad = [r for r in pred.get("rows", []) if (r.get("pointer") or {}).get("page") in pages]
            ok, detail = not bad, f"{len(bad)} output rows on noise page(s) {sorted(pages)}"
        elif t == "wrapped_description":
            bad = []
            for w in where:
                cont = w.get("continuation", {})
                on_cont = [r for r in pred.get("rows", []) if (r.get("pointer") or {}).get("page") == cont.get("page")
                           and (r.get("pointer") or {}).get("line") == cont.get("line")]
                ki = next((i for i, k in enumerate(key["rows"]) if _same_place(k.get("pointer") or {}, w["row"])), None)
                p = pred["rows"][k2p[ki]] if ki is not None and k2p.get(ki) is not None else None
                if on_cont or p is None or p.get("name") != w.get("name"):
                    bad.append(f"{w.get('name')!r}: got {p.get('name') if p else None!r}"
                               + (", row on continuation line" if on_cont else ""))
            ok, detail = not bad, "; ".join(bad) or f"{len(where)} wrapped names joined"
        elif t == "unrelated_table":
            bad = []
            for w in where:
                m = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", w.get("range", ""))
                lo, hi = (int(m.group(2)), int(m.group(4))) if m else (0, 0)
                for r in pred.get("rows", []):
                    p = r.get("pointer") or {}
                    rn = int(re.sub(r"[A-Z]", "", p.get("cell", "A0")) or 0)
                    if p.get("sheet") == w.get("sheet") and lo <= rn <= hi:
                        bad.append(p.get("cell"))
            ok, detail = not bad, f"{len(bad)} output rows inside the unrelated table" + (f": {bad[:5]}" if bad else "")
        elif t in ("numbers_as_text", "hidden_column"):
            fields = set()
            for w in where:
                fields |= set(w.get("fields") or [])
            if t == "hidden_column":
                fields = {"zugang"}
            g, n = _outcomes(key, pred, pairs, lambda k, f: not fields or f in fields)
            ok, detail = g == n, f"{sorted(fields) or 'all fields'}: {g}/{n} correct"
        elif t == "carry_over":
            g, n = _outcomes(key, pred, pairs, lambda k, f: k.get("kind") == "carry_over")
            bad = _wrong(key, pred, pairs)
            ok, detail = g == n and bad == 0, f"carry-over rows {g}/{n} correct, {bad} wrong values in the document"
        else:
            bad = _wrong(key, pred, pairs)
            ok, detail = bad == 0, f"{bad} wrong values in the document"
        res.append({"type": t, "pass": ok, "detail": detail.strip("; "),
                    "expected": pl.get("expected_behaviour", "")})
    return res


def main(pred_dir: str, corpus_dir: str | None = None) -> int:
    corpus = Corpus(Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS)
    fails = 0
    for doc_id, path in iter_predictions(Path(pred_dir)):
        key = corpus.key(doc_id)
        if not key or not key.get("planted"):
            continue
        for r in evaluate(load(path), key):
            fails += not r["pass"]
            print(("PASS " if r["pass"] else "FAIL ") + f"{doc_id:28s} {r['type']:28s} {r['detail']}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
