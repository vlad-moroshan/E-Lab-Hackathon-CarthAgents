"""Evaluation-only heuristic references, separate from runtime extraction.

Token references require both amount/sign agreement and a unique column position learned from other records.
Multi/weak references are diagnostics with no correctness credit. Clipped and unavailable values remain unresolved.
Explicit workbook pointers read source values and formula caches; source/key conflicts retain their observed amount.
No substring matching or shared glued-token boxes are accepted. Scans use fixed evaluation-only frame transforms.
"""

from __future__ import annotations

import statistics
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from dataclasses import dataclass

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils import column_index_from_string, get_column_letter

from carth.eval.frames import best_turn, centre_in, turn_box
from carth.numbers import parse_amount

TOL = 6.0  # points: how far a value may sit from its field's usual spot inside the row


@dataclass
class Ref:
    kind: str  # token | blank | cell | blank_cell | weak | none
    page: int | None = None
    bbox: list | None = None  # key frame
    alts: list | None = None  # kind "multi" (PDF): every acceptable token box
    cells: list | None = None  # kind "multi" (xlsx): every acceptable cell
    sheet: str | None = None
    cell: str | None = None
    why: str = ""
    observed: int | None = None  # source-truth value when a fixture key conflicts


def targets(key: dict) -> list[tuple[int, str, int]]:
    """(row index, field name, value) for every scored value: standard fields + net fields."""
    out = []
    for i, r in enumerate(key["rows"]):
        out += [(i, f, v) for f, v in r.get("fields", {}).items()]
        out += [(i, f"net:{f}", v) for f, v in r.get("net_fields", {}).items()]
    return out


def _cents(text: str, unit: str, ocr: bool) -> int | None:
    a = parse_amount(text, ocr=ocr)
    return None if a is None else a.cents(unit)


def _matches(tok: dict, f: str, value: int, printed: str, unit: str) -> bool:
    ocr = str(tok.get("src", "")).startswith("ocr")
    if f.startswith("net:"):  # signed, no printed string in the key
        return _cents(tok["text"], unit, ocr) == value
    c = _cents(tok["text"], unit, ocr)
    if c is None or not printed:
        return False
    return c == value if f == "umbuchung" else abs(c) == abs(value)


def pdf_refs(key: dict, tokens: list[dict] | None, page_sizes: dict[int, tuple[float, float]],
             text_layer: bool) -> tuple[dict, dict]:
    """References for a PDF. Returns (refs {(i, f): Ref}, turns {page: turn}). Token boxes are turned into the key
    frame per page (identity for text layers)."""
    unit = key["meta"]["unit"]
    rows_by_page = defaultdict(list)
    for r in key["rows"]:
        rows_by_page[r["pointer"]["page"]].append(r["pointer"]["bbox"])
    turns = {}
    toks_by_page = defaultdict(list)
    for t in tokens or []:
        toks_by_page[t["page"]].append(t)
    if tokens and not text_layer:
        for pg, toks in toks_by_page.items():
            W, H = page_sizes[pg]
            amounts = [t["bbox"] for t in toks if parse_amount(t["text"], ocr=True)]
            turns[pg] = best_turn(amounts, rows_by_page.get(pg, []), W, H)
            toks_by_page[pg] = [{**t, "bbox": turn_box(t["bbox"], turns[pg], W, H)} for t in toks]

    refs: dict = {}
    if tokens is None:
        for i, f, _ in targets(key):
            refs[(i, f)] = Ref("weak", page=key["rows"][i]["pointer"]["page"], bbox=key["rows"][i]["pointer"]["bbox"],
                               why="no reference tokens for this page image")
        return refs, turns

    def section(r):
        b = r["pointer"]["bbox"]
        return (r["pointer"]["page"], round(b[2] - b[0], -1), round(b[3] - b[1], -1))

    cands, offsets = {}, defaultdict(list)
    for i, f, v in targets(key):
        r = key["rows"][i]
        p, rb = r["pointer"]["page"], r["pointer"]["bbox"]
        printed = "" if f.startswith("net:") else r.get("printed", {}).get(f, "")
        inrow = [t for t in toks_by_page.get(p, []) if centre_in(t["bbox"], rb)]
        cs = [t for t in inrow if _matches(t, f, v, printed, unit)]
        cands[(i, f)] = (cs, printed, inrow)
        if len(cs) == 1 and r.get("flags", {}).get(f) != "cut_off":
            offsets[(section(r), f)].append((i, _anchors(cs[0]["bbox"], rb)))
    def learned(r, f, exclude):
        samples = [o for i, o in offsets.get((section(r), f), []) if i != exclude]
        if len(samples) < 3:
            return None
        med = tuple(statistics.median(o[k] for o in samples) for k in range(8))
        # Reject mixed layouts instead of averaging columns from separate sections.
        if sum(distance(o, med) <= TOL for o in samples) < .8 * len(samples):
            return None
        return med

    def distance(a, m):
        return max(abs(a[2] - m[2]), abs(a[4] - m[4])) if m[6] >= m[7] else max(abs(a[1] - m[1]), abs(a[5] - m[5]))

    for (i, f), (cs, printed, inrow) in cands.items():
        r = key["rows"][i]
        p, rb, v = r["pointer"]["page"], r["pointer"]["bbox"], (r.get("fields", {}) | {
            f"net:{k}": x for k, x in r.get("net_fields", {}).items()})[f]
        spot = learned(r, f, i)
        close = [t for t in cs if spot and distance(_anchors(t["bbox"], rb), spot) <= TOL]
        if r.get("flags", {}).get(f) == "cut_off":
            refs[(i, f)] = Ref("none", why="source characters clipped; no reconstructed reference")
        elif len(close) == 1:
            refs[(i, f)] = Ref("token", p, close[0]["bbox"], why="heuristic column learned from other records")
        elif cs:
            refs[(i, f)] = Ref("multi", p, rb, alts=[t["bbox"] for t in cs], why="field occurrence not uniquely verified")
        else:
            # A predicted blank rectangle is not proof of a real, identified empty amount cell.
            refs[(i, f)] = Ref("weak" if not text_layer or not printed else "none", p, rb,
                               why="no verified source occurrence or empty amount cell")
    # One printed occurrence cannot prove two different fields in the same record.
    used = defaultdict(list)
    for target, ref in refs.items():
        if ref.kind == "token":
            used[(target[0], ref.page, tuple(ref.bbox))].append(target)
    for same in used.values():
        if len(same) > 1:
            for target in same:
                refs[target].kind = "multi"
                refs[target].why = "source occurrence shared by unrelated fields"

    return refs, turns


def _anchors(b, rb) -> tuple:
    """(x0, cx, x1, y0, cy, y1) of box b relative to the row box origin, plus its width and height."""
    return (b[0] - rb[0], (b[0] + b[2]) / 2 - rb[0], b[2] - rb[0], b[1] - rb[1], (b[1] + b[3]) / 2 - rb[1],
            b[3] - rb[1], b[2] - b[0], b[3] - b[1])


def cell_cents(token, unit, field):
    """Read source literal/cache exactly. Never interpret a formula expression or missing cache as zero."""
    if token is None or token.get("kind") in ("formula_uncached", "date", "error"):
        return None
    value = token.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            scaled = Decimal(str(value)) * (100_000 if unit == "TEUR" else 100)
            cents = int(scaled) if scaled.is_finite() and scaled == scaled.to_integral_value() else None
        except (InvalidOperation, ValueError):
            return None
    elif isinstance(value, str):
        cents = _cents(value, unit, False)
    else:
        return None
    return cents if cents is None or field == "umbuchung" or field.startswith("net:") else abs(cents)


def xlsx_refs(key: dict, doc_path, tokens: list[dict]) -> dict:
    wb = load_workbook(doc_path, data_only=False)
    bounds = {ws.title: (ws.max_column, ws.max_row) for ws in wb}
    at = {(t["sheet"], t["cell"]): t for t in tokens}
    learned = defaultdict(set)

    def rc(coord):
        col = "".join(ch for ch in coord if ch.isalpha())
        return column_index_from_string(col), int(coord[len(col):])

    for r in key["rows"]:
        p = r["pointer"]
        ar = rc(p["cell"])[1]
        for f, coord in p.get("cells", {}).items():
            c, rr = rc(coord)
            learned[(p["sheet"], r.get("year"), r.get("kind"), f)].add((c, rr - ar))
    refs = {}
    for i, f, v in targets(key):
        r = key["rows"][i]
        p = r["pointer"]
        sh, ar = p["sheet"], rc(p["cell"])[1]
        coord = p.get("cells", {}).get(f)
        explicit = coord is not None
        if not coord:
            spots = learned.get((sh, r.get("year"), r.get("kind"), f), set())
            if len(spots) == 1:
                c, d = next(iter(spots))
                # An inferred field must stay inside this physical record.
                next_row = min((rc(x["pointer"]["cell"])[1] for x in key["rows"]
                                if x["pointer"]["sheet"] == sh and rc(x["pointer"]["cell"])[1] > ar), default=ar + 1)
                if ar <= ar + d < next_row:
                    coord = f"{get_column_letter(c)}{ar + d}"
        if not coord:
            refs[(i, f)] = Ref("weak", why="field column unresolved")
            continue
        token = at.get((sh, coord))
        if not explicit and (token is not None or v != 0):
            refs[(i, f)] = Ref("weak", why="inferred position is not a verified empty amount cell")
            continue
        observed = cell_cents(token, key["meta"]["unit"], f)
        c, rr = rc(coord)
        unavailable = False
        for t in tokens:
            if t.get("sheet") == sh and t.get("formula_ref") and t.get("cache_state") == "missing":
                c0, r0, c1, r1 = range_boundaries(t["formula_ref"])
                unavailable |= c0 <= c <= c1 and r0 <= rr <= r1
        truly_empty = (c <= bounds[sh][0] and rr <= bounds[sh][1] and token is None
                       and not isinstance(wb[sh][coord], MergedCell) and not unavailable
                       and wb[sh][coord].value is None and wb[sh][coord].data_type != "f")
        if truly_empty and (explicit or v == 0):
            refs[(i, f)] = Ref("blank_cell", sheet=sh, cell=coord, observed=0)
        elif observed is None:
            refs[(i, f)] = Ref("none", sheet=sh, cell=coord, why="source unavailable, nonnumeric or missing formula cache")
        else:
            refs[(i, f)] = Ref("cell", sheet=sh, cell=coord, observed=observed,
                               why="source/key conflict" if observed != v else "validated source cell")
    wb.close()
    return refs
