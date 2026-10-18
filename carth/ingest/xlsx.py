"""xlsx -> cell tokens. Keeps everything a reader needs to judge relevance later, decides nothing:
hidden rows / columns / sheets (f09 hides every asset row in an outline; f08_07 hides a stale draft column),
outline level, bold, number format, merged range, and for formulas both the formula text and the cached value that
Excel / LibreOffice saved. A formula without a cached value is kept as kind "formula_uncached" with value None:
it is not a blank cell and must never be read as zero.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries


def _hidden_cols(ws) -> set[int]:
    out = set()
    for key, dim in ws.column_dimensions.items():
        if dim.hidden:
            lo = dim.min or column_index_from_string(key)
            out.update(range(lo, (dim.max or lo) + 1))
    return out


def xlsx_tokens(path: Path) -> tuple[list[dict], list[dict]]:
    """Returns (sheets, tokens). One token per non-empty cell."""
    wb = load_workbook(path, data_only=True)
    wf = load_workbook(path, data_only=False)  # same cells, formulas as text
    sheets, tokens = [], []
    for ws in wb.worksheets:
        fs = wf[ws.title]
        hcols = _hidden_cols(ws)
        merged = {}
        for rng in ws.merged_cells.ranges:
            merged[f"{get_column_letter(rng.min_col)}{rng.min_row}"] = str(rng)
        sheets.append({"sheet": ws.title, "state": ws.sheet_state, "max_row": ws.max_row, "max_col": ws.max_column,
                       "hidden_cols": sorted(hcols), "merged_ranges": [str(r) for r in ws.merged_cells.ranges]})
        for row in ws.iter_rows():
            for c in row:
                v, fv = c.value, fs[c.coordinate].value
                fc = fs[c.coordinate]
                formula_kind = type(fv).__name__ if fc.data_type == "f" else None
                formula = (fv if isinstance(fv, str) else getattr(fv, "text", None) or repr(dict(fv))) if formula_kind else None
                if formula is None and (v is None or (isinstance(v, str) and not v.strip())):
                    continue
                if isinstance(v, (datetime, date)):
                    v = v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
                rd = ws.row_dimensions[c.row]
                tokens.append({
                    "sheet": ws.title, "cell": c.coordinate, "row": c.row, "col": c.column,
                    "text": formula if v is None else v if isinstance(v, str) else str(v),
                    "value": v,  # number / str / ISO date: the stored (cached) value, untouched; None if uncached
                    "kind": "formula_uncached" if formula and v is None else
                            "error" if c.data_type == "e" else
                            "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                            "date" if c.is_date else "text",
                    "formula": formula,
                    "formula_kind": formula_kind,
                    "cache_state": ("missing" if v is None else "present") if formula_kind else "literal",
                    "formula_ref": getattr(fv, "ref", None) if formula_kind else None,
                    "number_format": c.number_format,
                    "hidden": bool(rd.hidden or c.column in hcols or ws.sheet_state != "visible"),
                    "outline": rd.outlineLevel or 0,
                    "bold": bool(c.font and c.font.b),
                    "merged": merged.get(c.coordinate),
                    "src": "xlsx", "conf": 1.0,
                })
    return sheets, tokens


def empty_amount_cell(doc, sheet, coord):
    """A real empty cell inside an identified table area, excluding merges and unavailable formula ranges."""
    rr, cc = coordinate_to_tuple(coord)
    info = next((s for s in doc.get("sheets", []) if s["sheet"] == sheet), None)
    if not info or not (1 <= rr <= info["max_row"] and 1 <= cc <= info["max_col"]):
        return False
    def contains(rng):
        c0, r0, c1, r1 = range_boundaries(rng)
        return r0 <= rr <= r1 and c0 <= cc <= c1
    if any(contains(rng) for rng in info.get("merged_ranges", [])):
        return False
    for t in doc["tokens"]:
        if t.get("sheet") != sheet:
            continue
        if t["cell"] == coord:
            return False
        if t.get("formula_ref") and t.get("cache_state") == "missing" and contains(t["formula_ref"]):
            return False
    return True
