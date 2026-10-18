"""Stage 1: any hand-over file -> one token list (the evidence layer). Cached as out/tokens/<doc_id>.json.

Token ids ("t0", "t1", …) are what later stages (and the LLM) refer to; numbers are never re-typed.
"""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path

import pdfplumber

from carth.ingest.pdf_text import page_words
from carth.ingest.xlsx import xlsx_tokens


DOC_SUFFIXES = {".pdf", ".xlsx", ".xlsm"}
FRAME_VERSION = 2


def find_documents(root: Path) -> list[Path]:
    """Every hand-over document under root, by file type only (no answer keys, no file-name rules).
    Folders starting with "_" or "." (generator, profiles, caches) are skipped."""
    root = Path(root)
    if root.is_file():
        if root.name.startswith("~$"):
            return []
        if root.suffix.lower() not in DOC_SUFFIXES:
            raise ValueError(f"Unsupported document: {root}")
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(root)
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in DOC_SUFFIXES
                  and not p.name.startswith(("~$", "."))
                  and not any(s.startswith(("_", ".")) for s in p.relative_to(root).parts[:-1]))


def document_ids(root: Path) -> dict[Path, str]:
    paths = find_documents(root)
    counts = Counter(p.stem.casefold() for p in paths)
    return {p: p.stem if counts[p.stem.casefold()] == 1 else
            p.stem + "-" + hashlib.sha256(str(p.relative_to(root) if root.is_dir() else p.name).encode()).hexdigest()[:12]
            for p in paths}


def fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def cache_matches(doc: dict, path: Path) -> bool:
    return (doc.get("source") == str(Path(path).resolve()) and doc.get("sha256") == fingerprint(path)
            and doc.get("frame_version") == FRAME_VERSION)


def page_metadata(p):
    area = max(1, float(p.width * p.height))
    image_area = sum(max(0, im["x1"]-im["x0"]) * max(0, im["bottom"]-im["top"]) for im in p.images)
    # Selectable headings do not establish a readable image table. OCR keeps native text as separate evidence.
    needs = not p.chars or image_area / area > .15 or (len(p.chars) < 80 and len(p.curves) > 100)
    return {"page": p.page_number, "width": float(p.width), "height": float(p.height),
            "rotation": p.rotation, "has_text": bool(p.chars), "needs_ocr": needs,
            "image_area_ratio": round(min(image_area / area, 1), 4)}


def ingest(path: Path) -> dict:
    path = Path(path)
    if path.suffix.lower() not in DOC_SUFFIXES or path.name.startswith("~$"):
        raise ValueError(f"Unsupported document: {path}")
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        sheets, tokens = xlsx_tokens(path)
        doc = {"source": str(path), "kind": "xlsx", "sheets": sheets, "tokens": tokens}
    else:
        with pdfplumber.open(path) as pdf:
            pages = [page_metadata(p) for p in pdf.pages]
            tokens = [t for p in pdf.pages if p.chars for t in page_words(p)]
        # pages without a text layer (scans, glyphs-as-outlines) are filled in by the OCR stage (M3)
        kind = "pdf" if all(p["has_text"] for p in pages) else "pdf_ocr" if not tokens else "pdf_mixed"
        doc = {"source": str(path), "kind": kind, "pages": pages, "tokens": tokens}
    for i, t in enumerate(doc["tokens"]):
        t["id"] = f"t{i}"
    doc.update(source=str(path.resolve()), sha256=fingerprint(path), frame_version=FRAME_VERSION)
    return doc


def save(doc: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False), "utf-8")


def load(out: Path) -> dict:
    return json.loads(Path(out).read_text("utf-8"))
