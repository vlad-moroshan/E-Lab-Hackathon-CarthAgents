"""Stage 2 (M5): tokens -> typed tokens, lines, amount columns ("bands"). Geometry only: no keys, no model, no
layout-specific rules. Record structure (how many lines make one asset / class block, which line starts it) is
decided later by the layout spec (M6), which reads these lines; this stage only offers the evidence it needs:
line text, left-margin starts, vertical gaps and which amount sits in which band.

PDF / OCR: everything happens in the reading frame (`rbox`, text upright), per page.
  skew   - per page, the median slope of text lines is measured; above 0.1° the reading-frame boxes are turned
           straight before lines and bands are built (scans: a 2.5° tilt moves a column edge ~20 pt down a page).
           `bbox`, the pointer, always stays where the characters are on the page as given.
  align  - scanned pages sit at different horizontal offsets: each OCR page is shifted to match the right edges of
           the page with the most numbers (only when that clearly improves the match; text-layer pages never move)
  lines  - words are chained left to right: a word joins the open line whose last word is vertically closest
           (within half a text height), so lines follow a slight skew instead of breaking
  bands  - numeric tokens of the whole document are clustered by right edge (amounts are right-aligned; one page
           may hold a single total line, so columns are learned across pages); a cluster becomes a band if at least
           BAND_MIN lines use it. Amounts outside any band stay unbanded ("band": None). Pages with another layout
           (summary vs detail part) simply add their own clusters.
xlsx: a line is a sheet row, a band is a sheet column (hidden rows / columns are kept and marked).

Token types: "amount" (an amount with 2 decimals, or a lone "-"), "int" (an integer, e.g. TEUR amounts, ids, years:
the spec decides), "date", "glued" (no single amount, but splits into two), "text".

    python -m carth.layout out/tokens/f00_demo_02.json      prints the lines of a token file
"""

from __future__ import annotations

import math
import re
import statistics
import sys
from copy import deepcopy
from collections import defaultdict
from pathlib import Path

from carth.numbers import parse_amount, split_glued

DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.(\d{2}|\d{4})$|^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{4}$")
BAND_MIN = 3  # lines that must use a right edge before it counts as an amount column
BAND_TOL = 3.0  # points: right edges closer than this belong to one band
# integers are banded too: TEUR amounts have no decimals. Id / account columns then form bands of their own; the
# layout spec (M6) decides which bands carry amounts
NUMERIC = ("amount", "int", "glued")


def token_type(t: dict) -> str:
    if t.get("src") == "xlsx":
        return {"number": "amount", "date": "date", "formula_uncached": "formula"}.get(t.get("kind"), "text")
    s = t["text"]
    if DATE.match(s):
        return "date"
    ocr = str(t.get("src", "")).startswith("ocr")
    a = parse_amount(s, ocr=ocr)
    if a is not None:
        return "amount" if a.decimals == 2 or a.style == "dash" else "int"
    if split_glued(s, ocr=ocr):
        return "glued"
    return "text"


def _lines(toks: list[dict]) -> list[list[dict]]:
    """Chain words into lines in the reading frame."""
    if not toks:
        return []
    h = statistics.median(t["rbox"][3] - t["rbox"][1] for t in toks) or 1.0
    open_lines: list[list[dict]] = []
    for t in sorted(toks, key=lambda t: (t["rbox"][0], t["rbox"][1])):
        cy = (t["rbox"][1] + t["rbox"][3]) / 2
        best, dist = None, 0.5 * h
        for ln in open_lines:
            last = ln[-1]
            d = abs((last["rbox"][1] + last["rbox"][3]) / 2 - cy)
            if d <= dist and last["rbox"][0] <= t["rbox"][0]:
                best, dist = ln, d
        if best is None:
            open_lines.append([t])
        else:
            best.append(t)
    return sorted(open_lines, key=lambda ln: statistics.mean((t["rbox"][1] + t["rbox"][3]) / 2 for t in ln))


def _num_right(t: dict) -> float:
    """Right edge of a number's last digit in the reading frame: a trailing minus or bracket ("1.234,56-",
    "(1.234,56)") must not push a value into a neighbouring band (SAP pads positives with a space instead)."""
    s = t["text"]
    tail = len(s) - len(s.rstrip("-)–"))
    if not tail:
        return t["rbox"][2]
    w = (t["rbox"][2] - t["rbox"][0]) / max(1, len(s))
    return t["rbox"][2] - tail * w


def _skew(lines: list[list[dict]]) -> float:
    """Page tilt in degrees: median slope of the token centres along lines with 3+ tokens (least squares)."""
    slopes = []
    for ln in lines:
        if len(ln) < 3:
            continue
        xs = [(t["rbox"][0] + t["rbox"][2]) / 2 for t in ln]
        ys = [(t["rbox"][1] + t["rbox"][3]) / 2 for t in ln]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx > 100:  # the line spans some width
            slopes.append(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx)
    return math.degrees(math.atan(statistics.median(slopes))) if len(slopes) >= 3 else 0.0


def _straighten(toks: list[dict], deg: float) -> None:
    """Turn the reading-frame boxes by -deg around their centroid (in place); `bbox`, the pointer, is untouched."""
    a = math.radians(-deg)
    cs, sn = math.cos(a), math.sin(a)
    px = statistics.mean((t["rbox"][0] + t["rbox"][2]) / 2 for t in toks)
    py = statistics.mean((t["rbox"][1] + t["rbox"][3]) / 2 for t in toks)
    for t in toks:
        x0, y0, x1, y1 = t["rbox"]
        pts = [(cs * (x - px) - sn * (y - py) + px, sn * (x - px) + cs * (y - py) + py) for x in (x0, x1) for y in (y0, y1)]
        # keep the word's own size: only its centre moves (a turned box would grow by the tilt)
        cx, cy = statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts)
        w, h = x1 - x0, y1 - y0
        t["rbox_raw"], t["rbox"] = t["rbox"], [round(cx - w / 2, 2), round(cy - h / 2, 2), round(cx + w / 2, 2),
                                                round(cy + h / 2, 2)]


def _align(by: dict, lines: dict) -> dict:
    """Scanned pages sit at different horizontal offsets. Shift each OCR page's reading-frame boxes so its numeric
    right edges best match those of the page with the most numbers; returns {page: dx}. Text-layer pages are exact
    and never shifted (their summary / detail parts may legitimately use other columns)."""
    ocr_pages = [p for p, ts in by.items() if ts and str(ts[0].get("src", "")).startswith("ocr")]
    edges = {p: [_num_right(t) for t in by[p] if t["type"] in NUMERIC] for p in ocr_pages}
    if len(ocr_pages) < 2:
        return {}
    ref = max(ocr_pages, key=lambda p: len(edges[p]))
    ref_bands = [b["x1"] for b in _bands(lines[ref])]
    if not ref_bands:
        return {}

    def hits(xs, dx):
        return sum(any(abs(x + dx - b) <= BAND_TOL for b in ref_bands) for x in xs)

    shifts = {}
    for p in ocr_pages:
        if p == ref or not edges[p]:
            continue
        best = max((d / 2 for d in range(-120, 121)), key=lambda dx: (hits(edges[p], dx), -abs(dx)))
        if hits(edges[p], best) >= max(5, 1.2 * hits(edges[p], 0)):  # only a clear improvement moves a page
            shifts[p] = best
            for t in by[p]:
                t["rbox"] = [round(t["rbox"][0] + best, 2), t["rbox"][1], round(t["rbox"][2] + best, 2), t["rbox"][3]]
    return shifts


def _bands(lines: list[list[dict]]) -> list[dict]:
    """Right-edge clusters of amount tokens used by at least BAND_MIN lines."""
    edges = sorted((_num_right(t), i) for i, ln in enumerate(lines) for t in ln if t["type"] in NUMERIC)
    groups, cur = [], []
    for x, i in edges:
        if cur and x - cur[-1][0] > BAND_TOL:
            groups.append(cur)
            cur = []
        cur.append((x, i))
    if cur:
        groups.append(cur)
    bands = []
    for g in groups:
        if len({i for _, i in g}) >= BAND_MIN:
            xs = [x for x, _ in g]
            bands.append({"x1": round(statistics.median(xs), 2), "lo": round(min(xs), 2), "hi": round(max(xs), 2),
                          "n": len(g)})
    for k, b in enumerate(sorted(bands, key=lambda b: b["x1"])):
        b["id"] = k
    return sorted(bands, key=lambda b: b["x1"])


def _band_of(t: dict, bands: list[dict]) -> int | None:
    if t["type"] not in NUMERIC or not bands:
        return None
    x = _num_right(t)
    b = min(bands, key=lambda b: abs(b["x1"] - x))
    return b["id"] if abs(b["x1"] - x) <= BAND_TOL + 1 else None


def _pdf_page(page: dict, toks: list[dict], lines: list[list[dict]], bands: list[dict], frame: str, prefix: str) -> dict:
    h = statistics.median(t["rbox"][3] - t["rbox"][1] for t in toks) if toks else 1.0
    left = min((ln[0]["rbox"][0] for ln in lines), default=0.0)
    out, prev_bottom = [], None
    for k, ln in enumerate(lines):
        top, bottom = min(t["rbox"][1] for t in ln), max(t["rbox"][3] for t in ln)
        cells = [{"tid": t["id"], "type": t["type"], "band": _band_of(t, bands)} for t in ln]
        out.append({
            "id": f"{prefix}l{k}", "frame": frame, "y": [round(top, 2), round(bottom, 2)],
            "gap_above": None if prev_bottom is None else round((top - prev_bottom) / h, 2),  # in text heights
            "indent": round(ln[0]["rbox"][0] - left, 2),  # 0 = starts at the page's left margin
            "text": " ".join(t["text"] for t in ln), "cells": cells,
            "n_amounts": sum(c["type"] in ("amount", "glued") for c in cells),
        })
        prev_bottom = bottom
    return {"page": page["page"], "width": page.get("width"), "height": page.get("height"), "text_height": round(h, 2),
            "bands": bands, "lines": out}


def _xlsx_sheet(sheet: dict, toks: list[dict]) -> dict:
    rows = defaultdict(list)
    for t in toks:
        t["type"] = token_type(t)
        rows[t["row"]].append(t)
    cols = sorted({t["col"] for t in toks if t["type"] == "amount"})
    lines = []
    for r in sorted(rows):
        ln = sorted(rows[r], key=lambda t: t["col"])
        lines.append({"id": f"{sheet['sheet']}!{r}", "row": r, "hidden": any(t["hidden"] for t in ln),
                      "outline": max(t.get("outline", 0) for t in ln), "text": " | ".join(t["text"] for t in ln),
                      "cells": [{"tid": t["id"], "type": t["type"], "band": t["col"] if t["type"] == "amount" else None,
                                 "cell": t["cell"]} for t in ln],
                      "n_amounts": sum(t["type"] == "amount" for t in ln)})
    return {"sheet": sheet["sheet"], "state": sheet.get("state"), "hidden_cols": sheet.get("hidden_cols", []),
            "bands": [{"id": c, "col": c} for c in cols], "lines": lines}


def layout(doc: dict) -> dict:
    """Token file (carth.ingest / carth ocr output) -> {"kind", "pages" | "sheets", "tokens": {id: token}}."""
    toks = deepcopy(doc["tokens"])
    if doc["kind"] == "xlsx":
        by = defaultdict(list)
        for t in toks:
            by[t["sheet"]].append(t)
        parts = {"sheets": [_xlsx_sheet(s, by.get(s["sheet"], [])) for s in doc["sheets"]]}
    else:
        by = defaultdict(lambda: defaultdict(list))
        for t in toks:
            t["type"] = token_type(t)
            direction = int(t.get('dir', 0))
            angle = round(t.get('baseline_angle', direction), 3)
            frame = (t.get('src', 'pdf'), direction, angle)
            by[frame][t["page"]].append(t)
        pages = {p['page']: {**p, 'lines': [], 'bands': [], 'frames': []} for p in doc['pages']}
        next_band = 0
        for frame_index, (frame, frame_pages) in enumerate(sorted(by.items())):
            frame_id = f'f{frame_index}'
            lines, skews = {}, {}
            for pno, ts in frame_pages.items():
                for t in ts:
                    t['frame'] = frame_id
                lines[pno] = _lines(ts)
                skews[pno] = _skew(lines[pno])
                if abs(skews[pno]) > .1:
                    _straighten(ts, skews[pno])
                    lines[pno] = _lines(ts)
            shifts = _align(frame_pages, lines)
            bands = _bands([ln for lns in lines.values() for ln in lns])
            for band in bands:
                band['id'] += next_band
                band['frame'] = frame_id
            next_band += len(bands)
            for pno, ts in frame_pages.items():
                page = pages[pno]
                prefix = f'p{pno}' if len(by) == 1 else f'p{pno}{frame_id}'
                part = _pdf_page(page, ts, lines[pno], bands, frame_id, prefix)
                page['lines'].extend(part['lines'])
                page['bands'].extend(bands)
                page['frames'].append({'id':frame_id, 'source':frame[0], 'dir':frame[1], 'baseline_angle':frame[2],
                                       'skew_deg':round(skews[pno],3), 'dx':shifts.get(pno,0.0)})
                page['text_height'] = part['text_height']
        parts = {'pages': list(pages.values())}
    return {"source": doc.get("source"), "kind": doc["kind"], **parts, "tokens": {t["id"]: t for t in toks}}


def show(lay: dict, limit: int = 60) -> str:
    """Human-readable dump: one line per source line, amounts tagged with their band."""
    out = []
    for part in lay.get("pages", []) + lay.get("sheets", []):
        out.append(f"== page {part['page']}" if "page" in part else f"== sheet {part['sheet']}")
        out.append("   bands: " + ", ".join(f"{b['id']}@{b.get('x1', b.get('col'))}" for b in part["bands"]))
        for ln in part["lines"][:limit]:
            tags = " ".join(f"{lay['tokens'][c['tid']]['text']}" + (f"[{c['band']}]" if c["band"] is not None else "")
                            for c in ln["cells"])
            gap = ln.get("gap_above")
            out.append(f"{ln['id']:<10}{'' if gap is None else f'gap {gap:<5}'} {tags}")
    return "\n".join(out)


if __name__ == "__main__":
    from carth import ingest

    print(show(layout(ingest.load(Path(sys.argv[1]))), int(sys.argv[2]) if len(sys.argv) > 2 else 60))
