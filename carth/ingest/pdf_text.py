"""Text-layer PDF -> word tokens with exact page boxes.

Two traps handled here, both seen in the corpus:
  * fake bold: some prints draw every glyph twice, offset by a hair ("9977..330044") -> dedupe_chars()
  * turned pages: a landscape list printed 90° onto a portrait page -> words read bottom-to-top
Each token keeps `bbox` in page coordinates (points, top-left origin: the pointer format of the keys) and
`rbox` in the reading frame (as if the page were turned upright), which is what line/column grouping uses.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber


def page_words(page) -> list[dict]:
    p = page.dedupe_chars(tolerance=1)
    # no extra_attrs: splitting words on size would cut "12.138,62" before its last digit on turned pages,
    # where float noise gives one glyph size 3.3599… instead of 3.36… — read size / font from the chars instead
    ws = p.extract_words(keep_blank_chars=False, use_text_flow=False, line_dir_rotated="ltr",
                         char_dir_rotated="btt", return_chars=True)
    H = float(page.height)
    out = []
    for w in ws:
        c0 = w["chars"][0]
        w["size"], w["fontname"] = c0["size"], c0["fontname"]
        bbox = [round(w["x0"], 2), round(w["top"], 2), round(w["x1"], 2), round(w["bottom"], 2)]
        if w["upright"]:
            rbox = bbox
        else:  # content turned 90° counter-clockwise: reading x runs up the page, reading y runs right
            rbox = [round(H - w["bottom"], 2), round(w["x0"], 2), round(H - w["top"], 2), round(w["x1"], 2)]
        out.append({"page": page.page_number, "text": w["text"], "bbox": bbox, "rbox": rbox,
                    "upright": bool(w["upright"]), "size": round(w["size"], 2), "bold": "Bold" in w["fontname"],
                    "src": "pdf", "conf": 1.0})
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
