"""Stage 1: any hand-over file -> one token list (the evidence layer). Cached as out/tokens/<doc_id>.json.

Token ids ("t0", "t1", …) are what later stages (and the LLM) refer to; numbers are never re-typed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber

from carth.ingest.pdf_text import page_words
from carth.ingest.xlsx import xlsx_tokens


def ingest(path: Path) -> dict:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        sheets, tokens = xlsx_tokens(path)
        doc = {"source": str(path), "kind": "xlsx", "sheets": sheets, "tokens": tokens}
    else:
        with pdfplumber.open(path) as pdf:
            pages = [{"page": p.page_number, "width": float(p.width), "height": float(p.height),
                      "rotation": p.rotation, "has_text": bool(p.chars)} for p in pdf.pages]
            tokens = [t for p in pdf.pages if p.chars for t in page_words(p)]
        # pages without a text layer (scans, glyphs-as-outlines) are filled in by the OCR stage (M3)
        kind = "pdf" if all(p["has_text"] for p in pages) else "pdf_ocr" if not tokens else "pdf_mixed"
        doc = {"source": str(path), "kind": kind, "pages": pages, "tokens": tokens}
    for i, t in enumerate(doc["tokens"]):
        t["id"] = f"t{i}"
    return doc


def save(doc: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False), "utf-8")


def load(out: Path) -> dict:
    return json.loads(Path(out).read_text("utf-8"))
