"""Evaluation only (M5): does the line / band structure of carth.layout fit the answer keys?

Per PDF document (text layer or OCR tokens):
  in_band  - share of key amounts (located as a token with the printed text inside the key row) that sit in a band
  purity   - per field, share of its amounts in the field's most common band, averaged over amounts: 1.0 means a
             field always lands in one column (what the layout spec will rely on)
  rows_ok  - share of key rows whose lines belong to that row only (no line shared with another key row)
  lines    - most common number of lines per key row (3 for f03 blocks, 4 for SAP class blocks …)
OCR boxes are turned into the key frame per page first (carth.eval.frames), as in recall.

    python -m carth.eval.layout_metrics [TOKENS_DIR] [--formats pdf,scan,outline]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from carth import ingest
from carth.eval.frames import best_turn, centre_in, turn_box
from carth.eval.score import load_keys
from carth.layout import layout
from carth.numbers import parse_amount


def doc_metrics(key: dict, doc: dict) -> dict:
    lay = layout(doc)
    line_of, band_of = {}, {}
    for pg in lay["pages"]:
        for ln in pg["lines"]:
            for c in ln["cells"]:
                line_of[c["tid"]], band_of[c["tid"]] = ln["id"], c["band"]
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    rows_by_page = defaultdict(list)
    for r in key["rows"]:
        rows_by_page[r["pointer"]["page"]].append(r["pointer"]["bbox"])
    by_page = defaultdict(list)
    for t in doc["tokens"]:
        by_page[t["page"]].append(t)
    boxes = {}
    for pg, toks in by_page.items():
        turn = 0
        if toks and str(toks[0].get("src", "")).startswith("ocr"):
            W, H = sizes[pg]
            turn = best_turn([t["bbox"] for t in toks if parse_amount(t["text"], ocr=True)], rows_by_page[pg], W, H)
        for t in toks:
            boxes[t["id"]] = turn_box(t["bbox"], turn, *sizes[pg]) if turn else t["bbox"]

    found = in_band = 0
    field_bands = defaultdict(Counter)
    row_lines, line_rows = [], defaultdict(set)
    for i, r in enumerate(key["rows"]):
        p = r["pointer"]
        inrow = [t for t in by_page.get(p["page"], []) if centre_in(boxes[t["id"]], p["bbox"])]
        lines = {line_of[t["id"]] for t in inrow}
        row_lines.append(lines)
        for ln in lines:
            line_rows[ln].add(i)
        texts = Counter(t["text"] for t in inrow)
        for f, printed in r.get("printed", {}).items():
            if not printed or texts[printed] != 1:
                continue  # blank, unread, or not unique in its row: no clean position to judge
            t = next(t for t in inrow if t["text"] == printed)
            found += 1
            in_band += band_of[t["id"]] is not None
            if band_of[t["id"]] is not None:
                field_bands[f][band_of[t["id"]]] += 1
    pure = sum(c.most_common(1)[0][1] for c in field_bands.values())
    banded = sum(sum(c.values()) for c in field_bands.values())
    rows_ok = sum(1 for i, ls in enumerate(row_lines) if ls and all(line_rows[ln] == {i} for ln in ls))
    return {"found": found, "in_band": in_band / found if found else 0, "purity": pure / banded if banded else 0,
            "rows_ok": rows_ok / len(key["rows"]) if key["rows"] else 0,
            "lines": Counter(len(ls) for ls in row_lines).most_common(1)[0][0] if row_lines else 0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tokens", type=Path, nargs="?", default=Path("out/tokens"))
    ap.add_argument("--corpus", type=Path, default=Path("A3-Hackathon-Corpus"))
    ap.add_argument("--formats", default="pdf")
    a = ap.parse_args()
    print(f"{'doc':<28}{'fmt':<9}{'found':>7}{'in_band':>9}{'purity':>8}{'rows_ok':>9}{'lines':>7}")
    agg = defaultdict(list)
    for d, (_, key) in load_keys(a.corpus).items():
        fmt = key["meta"]["format"]
        tp = a.tokens / f"{d}.json"
        if fmt not in a.formats.split(",") or not tp.exists():
            continue
        m = doc_metrics(key, ingest.load(tp))
        agg[fmt].append(m)
        print(f"{d:<28}{fmt:<9}{m['found']:>7}{m['in_band']:>9.3f}{m['purity']:>8.3f}{m['rows_ok']:>9.3f}{m['lines']:>7}")
    for fmt, ms in agg.items():
        n = sum(m["found"] for m in ms)
        w = lambda k: sum(m[k] * m["found"] for m in ms) / n if n else 0  # noqa: E731
        print(f"{'TOTAL ' + fmt:<37}{n:>7}{w('in_band'):>9.3f}{w('purity'):>8.3f}"
              f"{sum(m['rows_ok'] for m in ms) / len(ms):>9.3f}")


if __name__ == "__main__":
    main()
