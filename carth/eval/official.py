"""Run the organisers' scorer (`_generator/check_corpus.py`, answer Q1) on our predictions.

check_corpus checks a key-schema JSON against its document: row laws and subtotal ties (`arithmetic`), every
printed string on the pointer's page (`pdf_checks`, text PDFs), every pointer cell holding the value
(`xlsx_checks`). We call those functions on each `<doc_id>.pred.json` and skip `name_hits`, which reads
confidential client folders we don't have. `pdf_checks` only checks the `perfect` variant; we always check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from carth.eval.score import _doc_path, load_keys


def _check_corpus(corpus: Path):
    sys.path.insert(0, str((corpus / "_generator").resolve()))
    import check_corpus  # noqa: PLC0415

    return check_corpus


def check(corpus: Path, pred_dir: Path, only: set[str] | None = None) -> int:
    cc = _check_corpus(corpus)
    n = fails = 0
    for doc_id, (kp, key) in load_keys(corpus).items():
        fmt = key["meta"]["format"]
        pp = pred_dir / f"{doc_id}.pred.json"
        if (only and fmt not in only) or not pp.exists():
            continue
        n += 1
        pred = json.loads(pp.read_text("utf-8"))
        pred.setdefault("meta", {}).update(format=fmt, variant="perfect")  # format is known from the file itself
        pred["meta"].setdefault("unit", key["meta"]["unit"])
        doc = _doc_path(kp, key)
        try:
            errs = [] if pred.get("rows") else ["no rows"]
            errs += (cc.xlsx_checks if fmt == "xlsx" else cc.pdf_checks)(pred, doc) + cc.arithmetic(pred)
        except Exception as e:  # a broken prediction is a FAIL, not a crash
            errs = [f"{type(e).__name__}: {e}"]
        fails += bool(errs)
        print(("FAIL " if errs else "OK   ") + doc_id + (": " + "; ".join(errs[:3]) + (f" (+{len(errs) - 3})" if len(errs) > 3 else "") if errs else ""))
    print(f"{n} predictions, {n - fails} OK, {fails} FAIL")
    return 1 if fails else 0
