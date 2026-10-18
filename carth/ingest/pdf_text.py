"""Text-layer PDF -> word tokens with exact page boxes.

Traps handled here:
  * fake bold: some prints draw every glyph twice, offset by a hair ("9977..330044") -> dedupe_chars()
  * text in any of the four directions (a landscape list turned onto a portrait page reads bottom-to-top; turned the
    other way it reads top-to-bottom; upside down it reads right-to-left). pdfplumber applies one setting to all
    rotated text, so chars are grouped by their actual direction (text matrix) and each group is read with its own
    word order — reading clockwise text with the counter-clockwise order would turn "12.345,67" into "76,543.21".
Each token keeps `bbox` in page coordinates (points, top-left origin, page as given: the pointer) and `rbox` in the
reading frame (as if that text were upright), which line/column grouping uses. `dir` is 0 / 90 / 180 / 270: the
counter-clockwise angle of the text baseline.
"""

from __future__ import annotations

from pathlib import Path
import math

import pdfplumber

# word order per direction: (char_dir, line_dir) for upright groups, (char_dir_rotated, line_dir_rotated) for turned
_ORDER = {0: ("ltr", "ttb"), 90: ("btt", "ltr"), 180: ("rtl", "btt"), 270: ("ttb", "rtl")}


def _direction(c) -> int:
    a, b, _, _, _, _ = c["matrix"]
    return (int(math.floor(math.degrees(math.atan2(b, a)) / 90 + .5)) * 90) % 360


def _rbox(bbox, d: int, W: float, H: float) -> list:
    x0, top, x1, bot = bbox
    if d == 90:  # reads bottom-to-top: reading x runs up the page, reading y runs right
        r = [H - bot, x0, H - top, x1]
    elif d == 270:  # reads top-to-bottom: reading x runs down the page, reading y runs left
        r = [top, W - x1, bot, W - x0]
    elif d == 180:
        r = [W - x1, H - bot, W - x0, H - top]
    else:
        r = [x0, top, x1, bot]
    return [round(v, 2) for v in r]


def page_words(page) -> list[dict]:
    p = page.dedupe_chars(tolerance=1)
    W, H = float(page.width), float(page.height)
    dirs = {_direction(c) for c in p.chars}
    out = []
    for d in sorted(dirs):
        sub = p.filter(lambda o, d=d: o.get("object_type") != "char" or _direction(o) == d)
        cd, ld = _ORDER[d]
        kw = {"char_dir": cd, "line_dir": ld} if d in (0, 180) else {"char_dir_rotated": cd, "line_dir_rotated": ld}
        # no extra_attrs: splitting words on size would cut "12.138,62" before its last digit on turned pages,
        # where float noise gives one glyph size 3.3599… instead of 3.36… — read size / font from the chars instead
        for w in sub.extract_words(keep_blank_chars=False, use_text_flow=False, return_chars=True, **kw):
            c0 = w["chars"][0]
            bbox = [round(w["x0"], 2), round(w["top"], 2), round(w["x1"], 2), round(w["bottom"], 2)]
            angle = math.degrees(math.atan2(c0["matrix"][1], c0["matrix"][0])) % 360
            residual = (angle - d + 180) % 360 - 180
            # Rotate individual glyph corners into a true reading frame; bbox stays on the original page.
            cs, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            points = [(cs*x-sn*y, sn*x+cs*y) for c in w["chars"]
                      for x in (c["x0"], c["x1"]) for y in (c["top"], c["bottom"])]
            rbox = ([round(min(x for x,y in points), 2), round(min(y for x,y in points), 2),
                     round(max(x for x,y in points), 2), round(max(y for x,y in points), 2)] if abs(residual) > .001
                    else _rbox(bbox, d, W, H))
            out.append({"page": page.page_number, "text": w["text"], "bbox": bbox, "rbox": rbox,
                        "baseline_angle": round(angle, 4), "skew": round(residual, 4),
                        "chars": [{"text": c["text"], "bbox": [round(c[k], 2) for k in ("x0", "top", "x1", "bottom")]} for c in w["chars"]],
                        "dir": d, "upright": d == 0, "size": round(c0["size"], 2),
                        "bold": "Bold" in c0["fontname"], "src": "pdf", "conf": 1.0})
    return out


def has_text_layer(path: Path) -> bool:
    with pdfplumber.open(path) as pdf:
        return any(p.chars for p in pdf.pages)


def pdf_tokens(path: Path) -> list[dict]:
    with pdfplumber.open(path) as pdf:
        return [t for page in pdf.pages for t in page_words(page)]


def text_in_bbox(words: list[dict], page: int, bbox, pad: float = 0.5) -> str:
    """Words of `page` whose centre lies inside bbox, in reading order."""
    x0, top, x1, bot = bbox
    sel = [w for w in words if w["page"] == page
           and x0 - pad <= (w["bbox"][0] + w["bbox"][2]) / 2 <= x1 + pad
           and top - pad <= (w["bbox"][1] + w["bbox"][3]) / 2 <= bot + pad]
    sel.sort(key=lambda w: (round(w["rbox"][1]), w["rbox"][0]))
    return " ".join(w["text"] for w in sel)
