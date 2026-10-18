#!/usr/bin/env python3
"""Completeness: did the output take every schedule line of the source document?

- text PDF: every text line with two or more amounts must lie inside some output row's box, or on a page the
  output lists as skipped (meta.skipped = [{"page": 3, "reason": "unrelated report"}, ...]);
  a covered line with more amounts than the output row took is noted (info: often columns the Arbeitsversion
  keeps but the score does not count, e.g. FK-Zinsen, Sonder-AfA, Bewegung netto)
- xlsx: every sheet row with two or more amount cells (visible columns) must be pointed at by some output row,
  or lie in a skipped range (meta.skipped = [{"sheet": "Sheet1", "rows": [68, 82], "reason": "forecast table"}])
- scan / outline PDF: not checkable without OCR, counted as such

    uv run python json_evaluator/check_completeness.py PRED_DIR [CORPUS_DIR]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (AMOUNT_TOKEN, DEFAULT_CORPUS, Corpus, centre_in, issue, iter_predictions, load,  # noqa: E402
                    parse_amount, pdf_words)

CHECK = "completeness"
_TEUR_TOKEN = re.compile(r"^-?\d{1,3}(?:\.\d{3})*-?$")


def _amounts(word: str, unit: str) -> int:
    n = len(AMOUNT_TOKEN.findall(word))
    if not n and unit == "TEUR" and _TEUR_TOKEN.match(word):
        n = 1
    return n


def _lines(words, tol: float = 2.0) -> list[list]:
    """Group words into printed lines by position: generators and SAP prints often draw every cell as its own
    block, so the PDF's own block/line structure does not give lines. Vertical text (rotated pages) groups by x."""
    vertical = sum(1 for w in words if (w[3] - w[1]) > 1.5 * (w[2] - w[0]) and len(w[4]) > 2) > len(words) / 2
    centre = (lambda w: (w[0] + w[2]) / 2) if vertical else (lambda w: (w[1] + w[3]) / 2)
    lines, last = [], None
    for w in sorted(words, key=centre):
        c = centre(w)
        if last is not None and c - last <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
        last = c
    return lines


def check_pdf(pred: dict, path: Path) -> tuple[list[dict], dict]:
    unit = pred["meta"].get("unit", "EUR")
    skipped = {s["page"] for s in pred["meta"].get("skipped", []) if "page" in s}
    stats = {"data_lines": 0, "covered": 0, "uncovered": 0, "short_rows": 0, "checkable": True}
    pages = pdf_words(path)
    if not any(pages):
        stats["checkable"] = False
        return [issue(CHECK, "info", "no text layer: completeness not checkable without OCR")], stats
    boxes = {}
    for r in pred["rows"]:
        p = r.get("pointer") or {}
        if p.get("bbox"):
            taken = sum(1 for f, s in (r.get("printed") or {}).items() if s)
            boxes.setdefault(p.get("page"), []).append((p["bbox"], taken, r))
    out = []
    for pno, words in enumerate(pages, 1):
        for ws in _lines(words):
            n = sum(_amounts(w[4], unit) for w in ws)
            if n < 2 or all(parse_amount(t, unit) == 0 for w in ws for t in AMOUNT_TOKEN.findall(w[4])):
                continue  # all-zero lines are check lines (Differenz), not schedule rows
            stats["data_lines"] += 1
            line = (min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws))
            text = " ".join(w[4] for w in ws)[:90]
            if pno in skipped:
                stats["covered"] += 1
                continue
            hits = [(b, t, r) for b, t, r in boxes.get(pno, []) if centre_in(line, b)]
            if not hits:
                stats["uncovered"] += 1
                out.append(issue(CHECK, "warn", f"page {pno}: line with {n} amounts not in output: {text!r}",
                                 page=pno))
                continue
            stats["covered"] += 1
            taken = sum(t for _, t, _ in hits)
            if taken and taken < n and len(hits) == 1:
                stats["short_rows"] += 1
                out.append(issue(CHECK, "info", f"line has {n} amounts, output row took {taken} (columns not mapped "
                                 f"to a field, e.g. FK-Zinsen, Sonder-AfA, Bewegung netto?): {text!r}", hits[0][2]))
    return out, stats


def _is_amount_cell(c, unit: str) -> bool:
    if type(c).__name__ == "MergedCell":  # covered by its merge range's top-left cell
        return False
    v = c.value
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, float):
        return True
    if isinstance(v, int):
        fmt = c.number_format or ""
        return "0.0" in fmt or "#,##" in fmt
    if isinstance(v, str):
        s = v.strip()
        return bool(s) and parse_amount(s, unit) is not None and ("," in s or unit == "TEUR")
    return False


def check_xlsx(pred: dict, path: Path) -> tuple[list[dict], dict]:
    import openpyxl
    from openpyxl.utils import coordinate_to_tuple

    unit = pred["meta"].get("unit", "EUR")
    pointed = {}
    for r in pred["rows"]:
        p = r.get("pointer") or {}
        rows = pointed.setdefault(p.get("sheet"), set())
        for c in [p.get("cell"), *(p.get("cells") or {}).values()]:
            if c:
                rows.add(coordinate_to_tuple(c)[0])
    skipped = {}
    for s in pred["meta"].get("skipped", []):
        if "sheet" in s:
            lo, hi = s.get("rows", [1, 10 ** 7])
            skipped.setdefault(s["sheet"], []).append((lo, hi))
    stats = {"data_lines": 0, "covered": 0, "uncovered": 0, "short_rows": 0, "checkable": True}
    out = []
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        hidden = {k for k, d in ws.column_dimensions.items() if d.hidden}
        for row in ws.iter_rows():
            cells = [c for c in row if _is_amount_cell(c, unit) and c.column_letter not in hidden]
            if len(cells) < 2 or all(parse_amount(str(c.value), unit) == 0 if isinstance(c.value, str)
                                     else c.value == 0 for c in cells):
                continue  # all-zero rows are check lines (Differenz), not schedule rows
            rn = row[0].row
            stats["data_lines"] += 1
            if rn in pointed.get(ws.title, set()) or any(lo <= rn <= hi for lo, hi in skipped.get(ws.title, [])):
                stats["covered"] += 1
                continue
            stats["uncovered"] += 1
            label = " ".join(str(c.value) for c in row if isinstance(c.value, str))[:60]
            out.append(issue(CHECK, "warn", f"{ws.title} row {rn}: {len(cells)} amounts not in output ({label!r})",
                             sheet=ws.title, sheet_row=rn))
    return out, stats


def check(pred: dict, source: Path | None) -> tuple[list[dict], dict]:
    if source is None:
        return [issue(CHECK, "info", "source document not found")], {"checkable": False}
    return (check_xlsx if source.suffix == ".xlsx" else check_pdf)(pred, source)


def main(pred_dir: str, corpus_dir: str | None = None) -> int:
    corpus, bad = Corpus(Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS), 0
    for doc_id, path in iter_predictions(Path(pred_dir)):
        res, st = check(load(path), corpus.source(doc_id))
        if not st.get("checkable"):
            print(f"SKIP {doc_id}: not checkable")
            continue
        bad += bool(st["uncovered"])
        print(("FAIL " if st["uncovered"] else "OK   ") + f"{doc_id} data lines {st['data_lines']} covered "
              f"{st['covered']} uncovered {st['uncovered']} short rows {st['short_rows']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
