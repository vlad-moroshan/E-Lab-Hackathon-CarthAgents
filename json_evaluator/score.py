#!/usr/bin/env python3
"""Score output JSONs against the answer keys with the challenge rule: +1 correct, 0 flagged blank, -3 wrong.

Each amount in a key row's `fields` is one value. Per value:
    correct  value equals the key and the pointer shows it (same cell / same page with the box on the key's line)
    blank    value null (flagged blank)                                   -> 0
    wrong    value differs, or right value with a pointer that misses     -> -3
    missing  key row or field not in the output                           -> 0 by default (--missing-as wrong: -3)
    extra    output rows the key does not have                            -> reported, not scored

For every wrong value it reports how far off it is and the likely cause: sign, unit scale (x100 / x1000),
column shift (equals another field of the row), row shift (equals the same field of a neighbouring row),
parse error (printed string right, number wrong), read error (printed string wrong), pointer only.
It also scores the flags against the key's flags (glued, non_tying, cut_off, transfer_incomplete) and
the non-amount fields (name, acq_date, nd_months, method).

    python3 "json evaluator/score.py" PRED_DIR [CORPUS_DIR] [--missing-as blank|wrong]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DEFAULT_CORPUS, Corpus, field_box, iter_predictions, load, match_rows, overlap_ratio  # noqa: E402

POINTS = {"correct": 1, "blank": 0, "wrong": -3, "missing": 0}
SECONDARY = ("name", "acq_date", "nd_months", "method")


def pointer_ok(k: dict, p: dict, f: str) -> bool:
    kp, pp = k.get("pointer") or {}, p.get("pointer") or {}
    if "sheet" in kp:
        want = (kp.get("cells") or {}).get(f)
        if pp.get("sheet") != kp["sheet"]:
            return False
        return want is None or (pp.get("cells") or {}).get(f) == want
    if pp.get("page") != kp.get("page"):
        return False
    return overlap_ratio(field_box(p, f), kp.get("bbox")) >= 0.5


def cause(f: str, pv: int, kv: int, k: dict, p: dict, neighbours: list[dict]) -> str:
    if pv == -kv:
        return "sign"
    for m in (100, 1000, 100_000):
        if kv and (pv == kv * m or pv * m == kv):
            return "unit_scale"
    others = {g: v for g, v in (k.get("fields") or {}).items() if g != f}
    if pv != 0 and pv in others.values():
        return "column_shift"
    if any((n.get("fields") or {}).get(f) == pv for n in neighbours if pv != 0):
        return "row_shift"
    kp, pp = (k.get("printed") or {}).get(f), (p.get("printed") or {}).get(f)
    if pp is not None and kp is not None:
        return "parse_error" if pp.replace(" ", "") == kp.replace(" ", "") else "read_error"
    if kv == 0:
        return "value_where_empty"
    if pv == 0:
        return "zero_for_value"
    return "other"


def magnitude(pv: int, kv: int) -> str:
    d = abs(pv - kv)
    if d <= 100:
        return "<=1 EUR"
    rel = d / max(abs(kv), 1)
    return "<=1%" if rel <= 0.01 else "<=10%" if rel <= 0.10 else "<=100%" if rel <= 1 else ">100%"


def score_doc(pred: dict, key: dict, missing_as: str = "blank") -> dict:
    pts = dict(POINTS, missing=POINTS["wrong"] if missing_as == "wrong" else 0)
    krows, prows = key["rows"], pred.get("rows", [])
    pairs, extra = match_rows(krows, prows)
    counts, by_field, by_kind = Counter(), defaultdict(Counter), defaultdict(Counter)
    causes, mags, wrong = Counter(), Counter(), []
    flag_stats = defaultdict(Counter)
    sec = defaultdict(Counter)

    for ki, pi in pairs:
        k = krows[ki]
        p = prows[pi] if pi is not None else None
        nb = [krows[j] for j in (ki - 1, ki + 1) if 0 <= j < len(krows)]
        for f, kv in (k.get("fields") or {}).items():
            if p is None or f not in (p.get("fields") or {}):
                o = "missing"
            else:
                pv = p["fields"][f]
                if pv is None:
                    o = "blank"
                elif pv == kv and pointer_ok(k, p, f):
                    o = "correct"
                else:
                    o = "wrong"
                    c = "pointer_only" if pv == kv else cause(f, pv, kv, k, p, nb)
                    causes[c] += 1
                    if pv != kv:
                        mags[magnitude(pv, kv)] += 1
                    wrong.append({"row": f"{k.get('year')} {k.get('kind')} "
                                         f"{k.get('asset_no') or k.get('class') or k.get('position') or ''}",
                                  "field": f, "pred": pv, "key": kv, "cause": c,
                                  "printed_pred": (p.get("printed") or {}).get(f),
                                  "printed_key": (k.get("printed") or {}).get(f)})
            counts[o] += 1
            by_field[f][o] += 1
            by_kind[k.get("kind")][o] += 1

        # flags: the key's flag types on this row, caught or not
        kf, pf = k.get("flags") or {}, (p.get("flags") or {}) if p else {}
        for f, reason in kf.items():
            hit = bool(pf) if f == "*" else (f in pf or "*" in pf or
                                              (p is not None and (p.get("fields") or {}).get(f) is None))
            flag_stats[reason]["caught" if hit else "missed"] += 1
        if p is not None:
            for f in pf:
                if f not in kf and "*" not in kf:
                    flag_stats["(not in key)"]["extra"] += 1
            for s in SECONDARY:
                if k.get(s) not in (None, ""):
                    sec[s]["correct" if str(p.get(s)) == str(k[s]) else "wrong"] += 1

    score = sum(pts[o] * n for o, n in counts.items())
    km, pm = key["meta"], pred.get("meta", {})
    meta_diff = {m: [pm.get(m), km.get(m)] for m in ("unit", "years", "period_end", "doc_type") if pm.get(m) != km.get(m)}
    total = sum(counts.values())
    return {
        "doc_id": km["doc_id"], "family": km.get("family"), "format": km.get("format"), "variant": km.get("variant"),
        "values": total, "score": score, "max_score": total,
        "score_pct": round(100 * score / total, 2) if total else 0.0,
        "counts": dict(counts), "precision": round(counts["correct"] / max(counts["correct"] + counts["wrong"], 1), 4),
        "coverage": round(counts["correct"] / max(total, 1), 4),
        "rows": {"key": len(krows), "pred": len(prows), "matched": sum(1 for _, p in pairs if p is not None),
                 "extra": len(extra)},
        "by_field": {f: dict(c) for f, c in by_field.items()}, "by_kind": {k: dict(c) for k, c in by_kind.items()},
        "wrong_causes": dict(causes), "wrong_magnitude": dict(mags), "wrong_values": wrong,
        "flags": {r: dict(c) for r, c in flag_stats.items()}, "secondary": {s: dict(c) for s, c in sec.items()},
        "meta_diff": meta_diff,
        "extra_rows": [f"{prows[i].get('year')} {prows[i].get('kind')} {prows[i].get('asset_no') or ''}"
                       for i in extra][:50],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pred_dir")
    ap.add_argument("corpus_dir", nargs="?", default=str(DEFAULT_CORPUS))
    ap.add_argument("--missing-as", choices=("blank", "wrong"), default="blank")
    a = ap.parse_args(argv)
    corpus = Corpus(Path(a.corpus_dir))
    tot = Counter()
    for doc_id, path in iter_predictions(Path(a.pred_dir)):
        key = corpus.key(doc_id)
        if key is None:
            print(f"SKIP {doc_id}: no answer key")
            continue
        r = score_doc(load(path), key, a.missing_as)
        c = r["counts"]
        tot.update(c)
        tot["score"] += r["score"]
        tot["values"] += r["values"]
        print(f"{doc_id:28s} score {r['score']:6d}/{r['values']:<5d} ({r['score_pct']:6.2f}%)  correct "
              f"{c.get('correct', 0):5d} blank {c.get('blank', 0):4d} wrong {c.get('wrong', 0):4d} "
              f"missing {c.get('missing', 0):4d}" + (f"  causes {r['wrong_causes']}" if r["wrong_causes"] else ""))
    if tot["values"]:
        print(f"{'TOTAL':28s} score {tot['score']}/{tot['values']} ({100 * tot['score'] / tot['values']:.2f}%)  "
              f"correct {tot['correct']} blank {tot['blank']} wrong {tot['wrong']} missing {tot['missing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
