"""Our stand-in for the leaderboard scorer: +1 correct, 0 blank, -3 wrong (brief), matched by pointer location.

Prediction file `<doc_id>.pred.json`: the submission format, i.e. the `.key.json` schema (organiser answer Q2):
    {"meta": {...}, "rows": [{"kind", "year", ..., "fields": {f: cents | None}, "printed": {f: text},
                              "pointer": {"page", "line", "bbox"} | {"sheet", "cell", "cells": {f: coord}},
                              "flags": {...}}], "planted": [...]}
Optionally a row may carry "pointers": {f: {"page", "bbox"} | {"sheet", "cell"}}: a tighter per-value pointer that
overrides the row pointer for that field.

A predicted value is matched to the key row whose location holds its pointer (xlsx: the exact cell of that field;
PDF: same page, pointer centre inside the key row's bbox). Scored per key (row, field):
  - no prediction                         -> 0 (blank)
  - value == key and pointer shows it     -> +1
  - anything else                         -> -3
A predicted value that matches no key cell/row is an `extra` and also costs -3 (conservative: never emit junk).
"Pointer shows it" for text PDFs: the key's printed string is in the text inside the pointer bbox (as in
check_corpus.pdf_checks); for scans/outlines (no text layer) the row containment is all we can check.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from carth.ingest.pdf_text import pdf_tokens, text_in_bbox

WRONG, RIGHT = -3, 1
PAD = 1.5  # points of slack around key row bboxes for pointer containment (bboxes are rounded to 0.1 pt)
# Key flags whose printed text is not fully on the page by design (assumption 5 in docs/CHALLENGE_UNDERSTANDING.md):
# the value is scored, the "pointer shows it" text check is skipped. Revisit once the organisers answer Q6/Q7.
NO_TEXT_CHECK = {"cut_off"}


@dataclass
class DocScore:
    doc_id: str
    family: str
    format: str
    variant: str
    total: int = 0  # scored key values
    right: int = 0
    wrong: int = 0
    blank: int = 0
    extra: int = 0
    errors: list = field(default_factory=list)  # first few wrong values, for error analysis

    @property
    def score(self) -> int:
        return RIGHT * self.right + WRONG * (self.wrong + self.extra)


def load_keys(corpus: Path) -> dict[str, tuple[Path, dict]]:
    out = {}
    for p in sorted(corpus.rglob("*.key.json")):
        if any(s.startswith(("_", ".")) for s in p.relative_to(corpus).parts):
            continue
        k = json.loads(p.read_text("utf-8"))
        out[k["meta"]["doc_id"]] = (p, k)
    return out


def _doc_path(key_path: Path, key: dict) -> Path:
    return key_path.with_name(key["meta"]["doc_id"] + (".xlsx" if key["meta"]["format"] == "xlsx" else ".pdf"))


def _field_pointer(prow: dict, f: str) -> dict | None:
    if f in prow.get("pointers", {}):
        return prow["pointers"][f]
    p = prow.get("pointer")
    if not p:
        return None
    if "sheet" in p:
        return {"sheet": p["sheet"], "cell": p.get("cells", {}).get(f, p.get("cell"))}
    return {"page": p.get("page"), "bbox": p.get("bbox")}


def _rownum(coord: str) -> int:
    return int("".join(ch for ch in coord if ch.isdigit()))


def _inside(bbox, row_bbox) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    x0, top, x1, bot = row_bbox
    return x0 - PAD <= cx <= x1 + PAD and top - PAD <= cy <= bot + PAD


def score_doc(key_path: Path, key: dict, pred: dict | None) -> DocScore:
    m = key["meta"]
    ds = DocScore(m["doc_id"], m["family"], m["format"], m["variant"])
    targets = {(i, f) for i, r in enumerate(key["rows"]) for f in r.get("fields", {})}
    ds.total = len(targets)
    is_xlsx = m["format"] == "xlsx"
    words = pdf_tokens(_doc_path(key_path, key)) if m["format"] == "pdf" else None

    # index of key locations
    by_cell = {}  # (sheet, coord) -> (row idx, field)
    by_xrow = {}  # (sheet, sheet row) -> row idx: for fields the key prints nowhere (blank zero, no cell)
    by_page = defaultdict(list)  # page -> [(row idx, bbox)]
    for i, r in enumerate(key["rows"]):
        p = r["pointer"]
        if is_xlsx:
            for f, coord in p.get("cells", {}).items():
                by_cell[(p["sheet"], coord)] = (i, f)
            for coord in [p["cell"], *p.get("cells", {}).values()]:
                by_xrow.setdefault((p["sheet"], _rownum(coord)), i)
        else:
            by_page[p["page"]].append((i, p["bbox"]))

    seen: dict[tuple, int] = {}  # (row idx, field) -> points awarded
    for prow in (pred or {}).get("rows", []):
        for f, v in prow.get("fields", {}).items():
            if v is None:
                continue  # flagged blank
            ptr = _field_pointer(prow, f)
            hit = None
            if ptr and is_xlsx and "cell" in ptr:
                loc = by_cell.get((ptr.get("sheet"), ptr["cell"]))
                if loc:
                    hit = (loc[0], f)
                else:  # a field with no cell of its own: only a zero that is not printed can live here
                    i = by_xrow.get((ptr.get("sheet"), _rownum(ptr["cell"])))
                    cells = key["rows"][i]["pointer"].get("cells", {}) if i is not None else {}
                    hit = (i, f) if i is not None and f not in cells else None
            elif ptr and not is_xlsx and "bbox" in ptr:
                rows = [i for i, b in by_page.get(ptr.get("page"), []) if _inside(ptr["bbox"], b)]
                hit = (rows[0], f) if rows else None
            if hit is None or hit not in targets or hit in seen:
                ds.extra += 1
                if len(ds.errors) < 8:
                    ds.errors.append({"extra": f, "value": v, "pointer": ptr})
                continue
            krow = key["rows"][hit[0]]
            ok = v == krow["fields"][f]
            if ok and is_xlsx and f in krow["pointer"].get("cells", {}):
                ok = by_cell.get((ptr["sheet"], ptr["cell"])) == hit
            if ok and words is not None and krow.get("flags", {}).get(f) not in NO_TEXT_CHECK:
                printed = krow.get("printed", {}).get(f, "")
                if printed:
                    t = text_in_bbox(words, ptr["page"], ptr["bbox"])
                    ok = printed in t or printed in t.replace(" ", "")
            seen[hit] = RIGHT if ok else WRONG
            if not ok and len(ds.errors) < 8:
                ds.errors.append({"row": hit[0], "field": f, "pred": v, "key": krow["fields"][f],
                                  "printed": krow.get("printed", {}).get(f)})
    ds.right = sum(1 for s in seen.values() if s == RIGHT)
    ds.wrong = sum(1 for s in seen.values() if s == WRONG)
    ds.blank = ds.total - len(seen)
    return ds


def score_corpus(corpus: Path, pred_dir: Path, only: set[str] | None = None) -> list[DocScore]:
    out = []
    for doc_id, (kp, key) in load_keys(corpus).items():
        if only and key["meta"]["format"] not in only:
            continue
        pp = pred_dir / f"{doc_id}.pred.json"
        pred = json.loads(pp.read_text("utf-8")) if pp.exists() else None
        out.append(score_doc(kp, key, pred))
    return out


def report(scores: list[DocScore], verbose: bool = False) -> str:
    def agg(name, ss):
        t = sum(s.total for s in ss)
        sc = sum(s.score for s in ss)
        r, w, b, e = (sum(getattr(s, a) for s in ss) for a in ("right", "wrong", "blank", "extra"))
        pct = 100 * sc / t if t else 0
        return f"{name:<28}{len(ss):>4}{t:>7}{sc:>8}{pct:>7.1f}%{r:>7}{w:>6}{b:>7}{e:>6}"

    head = f"{'group':<28}{'docs':>4}{'vals':>7}{'score':>8}{'pct':>8}{'right':>7}{'wrong':>6}{'blank':>7}{'extra':>6}"
    lines = [head, "-" * len(head)]
    for key in ("family", "format", "variant"):
        groups = defaultdict(list)
        for s in scores:
            groups[getattr(s, key)].append(s)
        lines += [agg(f"{key}={g}", ss) for g, ss in sorted(groups.items())] + [""]
    lines.append(agg("TOTAL", scores))
    if verbose:
        lines.append("")
        for s in scores:
            lines.append(agg(s.doc_id, [s]))
            lines += [f"    {e}" for e in s.errors[:3]]
    return "\n".join(lines)


def oracle_pred(key: dict, mode: str = "key") -> dict:
    """mode 'key': the answer key itself as a submission (must score max). 'empty': no rows (must score 0)."""
    return {**key, "rows": key["rows"] if mode == "key" else [], "planted": key.get("planted", []) if mode == "key" else []}
