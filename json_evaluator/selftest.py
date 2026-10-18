#!/usr/bin/env python3
"""Self-test: plant known mistakes in copies of answer keys and assert every check catches its mistake.

    .venv/bin/python "json evaluator/selftest.py" [CORPUS_DIR]
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_all  # noqa: E402
from common import DEFAULT_CORPUS, Corpus  # noqa: E402


def first(rows, pred):
    return next(i for i, r in enumerate(rows) if pred(r))


def nonzero_asset(f1, f2=None):
    return lambda r: r["kind"] == "asset" and r["fields"].get(f1) and (f2 is None or (
        r["fields"].get(f2) and r["fields"][f1] != r["fields"][f2]))


def m_off_by_cent(d):
    i = first(d["rows"], nonzero_asset("ahk_open"))
    d["rows"][i]["fields"]["ahk_open"] += 1
    d["rows"][i]["printed"].pop("ahk_open", None)


def m_column_shift(d):
    i = first(d["rows"], nonzero_asset("ahk_open", "kum_afa_open"))
    f = d["rows"][i]["fields"]
    f["ahk_open"], f["kum_afa_open"] = f["kum_afa_open"], f["ahk_open"]
    d["rows"][i]["printed"].clear()


def m_scale(d):
    i = first(d["rows"], nonzero_asset("ahk_close"))
    d["rows"][i]["fields"]["ahk_close"] *= 100
    d["rows"][i]["printed"].clear()


def m_flagged_blank(d):
    i = first(d["rows"], nonzero_asset("afa_gj"))
    d["rows"][i]["fields"]["afa_gj"] = None
    d["rows"][i].setdefault("flags", {})["afa_gj"] = "read_doubt"


def m_unflagged_blank(d):
    i = first(d["rows"], nonzero_asset("afa_gj"))
    d["rows"][i]["fields"]["afa_gj"] = None


def m_drop_row(d):
    del d["rows"][first(d["rows"], lambda r: r["kind"] == "asset")]


def m_wrong_page(d):
    i = first(d["rows"], lambda r: r["kind"] == "asset")
    d["rows"][i]["pointer"]["page"] = 2


def m_wrong_cell(d):
    i = first(d["rows"], nonzero_asset("zugang"))
    d["rows"][i]["pointer"]["cells"]["zugang"] = "B2"


def m_negative(d):
    i = first(d["rows"], nonzero_asset("kum_afa_open"))
    d["rows"][i]["fields"]["kum_afa_open"] *= -1
    d["rows"][i]["printed"].clear()


def m_unflag_non_tying(d):
    for r in d["rows"]:
        if "non_tying" in (r.get("flags") or {}).values():
            r.pop("flags")


def m_extra_row_on_noise(d):
    r = copy.deepcopy(d["rows"][0])
    r["pointer"] = {"page": 1, "line": 1, "bbox": [0, 0, 595.3, 841.9]}
    r["asset_no"] = "999999"
    d["rows"].append(r)


def m_bad_printed(d):
    i = first(d["rows"], nonzero_asset("ahk_open"))
    d["rows"][i]["printed"]["ahk_open"] = "1,00"


# (name, doc_id, mutation, assertion on the report)
CASES = [
    ("clean key scores 100%", "f00_demo_02", None,
     lambda r: r["score"]["score_pct"] == 100 and not any(c["summary"]["error"] for c in r["checks"].values())),
    ("off by one cent -> wrong, law broken", "f00_demo_02", m_off_by_cent,
     lambda r: r["score"]["counts"]["wrong"] == 1 and r["checks"]["laws"]["summary"]["error"] >= 1
     and r["checks"]["pointers"]["summary"]["error"] >= 1),
    ("swapped columns -> column_shift", "f00_demo_02", m_column_shift,
     lambda r: r["score"]["wrong_causes"].get("column_shift") == 2),
    ("x100 -> unit_scale", "f00_demo_02", m_scale, lambda r: r["score"]["wrong_causes"].get("unit_scale") == 1),
    ("flagged blank -> 0 points", "f00_demo_02", m_flagged_blank,
     lambda r: r["score"]["counts"]["blank"] == 1 and r["score"]["score"] == r["score"]["values"] - 1
     and r["checks"]["schema"]["summary"]["error"] == 0),
    ("unflagged blank -> schema error", "f00_demo_02", m_unflagged_blank,
     lambda r: r["checks"]["schema"]["summary"]["error"] == 1),
    ("dropped row -> missing + uncovered line", "f00_demo_02", m_drop_row,
     lambda r: r["score"]["counts"]["missing"] == 12 and r["checks"]["completeness"]["stats"]["uncovered"] == 1),
    ("wrong page -> pointer_only wrong", "f00_demo_02", m_wrong_page,
     lambda r: r["score"]["wrong_causes"].get("pointer_only") == 12 and r["checks"]["pointers"]["summary"]["error"]),
    ("wrong cell -> pointer_only wrong", "f00_demo_01", m_wrong_cell,
     lambda r: r["score"]["wrong_causes"].get("pointer_only") == 1 and r["checks"]["pointers"]["summary"]["error"]),
    ("negative depreciation -> schema error, sign", "f00_demo_02", m_negative,
     lambda r: r["checks"]["schema"]["summary"]["error"] == 1 and r["score"]["wrong_causes"].get("sign") == 1),
    ("unflagged non-tying subtotal -> totals error, flag missed", "f00_demo_04", m_unflag_non_tying,
     lambda r: r["checks"]["totals"]["summary"]["error"] >= 1 and r["score"]["flags"]["non_tying"].get("missed") == 1),
    ("row on a noise page -> planted fail", "f03_block_spiegel_06", m_extra_row_on_noise,
     lambda r: any(p["type"] == "noise_page_cover" and not p["pass"] for p in r["planted"])),
    ("printed does not match value -> schema + pointer error", "f00_demo_02", m_bad_printed,
     lambda r: r["checks"]["schema"]["summary"]["error"] == 1 and r["checks"]["pointers"]["summary"]["error"] == 1),
]


def main(corpus_dir: str | None = None) -> int:
    corpus = Corpus(Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS)
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, doc_id, mut, ok in CASES:
            d = corpus.key(doc_id)
            if mut:
                mut(d)
            p = Path(tmp) / f"{doc_id}.json"
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            rep = run_all.evaluate_doc(doc_id, p, corpus, "blank")
            try:
                passed = bool(ok(rep))
            except Exception as e:  # a missing key in the report is a failed assertion
                passed, name = False, f"{name} ({type(e).__name__}: {e})"
            fails += not passed
            print(("PASS " if passed else "FAIL ") + name)
    print(f"{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
