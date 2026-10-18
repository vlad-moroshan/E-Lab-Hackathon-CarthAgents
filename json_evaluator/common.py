"""Shared helpers for the evaluator: the output format, row laws, amount parsing, loading and row matching.

The output format is the answer-key format (A3-Hackathon-Corpus/*/<doc_id>.key.json) with the local evaluator
extensions of carth/eval/score.py: null amounts and per-value `pointers`. Files are named <doc_id>.pred.json
(out/pred/), <doc_id>.json or <doc_id>.key.json.
    {"meta": {doc_id, unit, years, ...},
     "rows": [{kind, year, asset_no, sub_no, class, account, position, name, ...,
               "fields":   {field: int cents | null},     # null = left blank
               "printed":  {field: str},                  # the characters the value was read from
               "pointer":  {page, line, bbox} | {sheet, cell, cells: {field: "C8"}},
               "pointers": {field: {page, bbox} | {sheet, cell}},   # optional, tighter per-value pointer
               "flags":    {field | "*": reason}}]}       # every blank needs a flag
Amounts are int cents, magnitudes; only `umbuchung` carries a sign. An empty amount cell is 0.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = ROOT / "A3-Hackathon-Corpus"

AMOUNT_FIELDS = ("ahk_open", "zugang", "abgang", "abgang_bw", "umbuchung", "ahk_close", "kum_afa_open", "afa_gj",
                 "afa_abgang", "zuschreibung", "kum_afa_close", "bw_close", "bw_prev")
SIGNED_FIELDS = {"umbuchung"}
TOTAL_KINDS = ("class_subtotal", "account_subtotal", "position_subtotal", "grand_total", "carry_over")
ROW_KINDS = ("asset", *TOTAL_KINDS)
ID_FIELDS = ("asset_no", "sub_no", "class", "account", "position", "level")
# flag reasons the answer keys use; a pipeline may add its own (read_doubt, ocr_low_conf, ...)
KEY_FLAG_REASONS = ("glued", "non_tying", "cut_off", "transfer_incomplete")
# values not read from their own characters: rebuilt from the row laws (cut_off) or implied by the other rows
# (transfer_incomplete: the key holds the implied transfer, not the printed one); pointer re-read skips them
DERIVED_FLAGS = ("cut_off", "transfer_incomplete")

# (target, {term: sign}, terms that count as 0 when the layout does not print them)
# Same laws as _generator/check_corpus.py; they hold on every row of the sample keys.
LAWS = [
    ("ahk_close", {"ahk_open": 1, "zugang": 1, "abgang": -1, "umbuchung": 1}, {"umbuchung"}),
    ("kum_afa_close", {"kum_afa_open": 1, "afa_gj": 1, "afa_abgang": -1, "zuschreibung": -1}, {"zuschreibung"}),
    ("bw_close", {"ahk_close": 1, "kum_afa_close": -1}, set()),
    ("bw_prev", {"ahk_open": 1, "kum_afa_open": -1}, set()),
    ("bw_close", {"bw_prev": 1, "zugang": 1, "umbuchung": 1, "abgang_bw": -1, "afa_gj": -1, "zuschreibung": 1},
     {"umbuchung", "zuschreibung"}),
]
# year N closing value -> year N+1 opening value
CARRY_FORWARD = {"ahk_close": "ahk_open", "kum_afa_close": "kum_afa_open", "bw_close": "bw_prev"}


def unit_scale(unit: str) -> int:
    """Cents per printed unit."""
    return 100_000 if unit == "TEUR" else 100


def tolerance(unit: str, n_terms: int) -> int:
    """TEUR amounts are rounded one by one: allow half a unit per term."""
    return 50_000 * n_terms if unit == "TEUR" else 0


_AMOUNT = re.compile(r"^\(?([+-]?)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d+))?\)?(-?)$")
AMOUNT_TOKEN = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})*,\d{2}-?|[+-]?\d+,\d{2}-?")


def parse_amount(text: str | None, unit: str = "EUR") -> int | None:
    """German-format amount as printed ('1.234,56', '1.234,56-', '-314.602,06', '186' in TEUR) -> signed cents.
    '' -> 0. Anything else -> None."""
    if text is None:
        return None
    s = str(text).strip().replace("−", "-").replace(" ", "").replace(" ", "")
    if s in ("", "-", "\u2013", "\u2014"):  # empty or a dash: printed zero
        return 0
    m = _AMOUNT.match(s)
    if not m:
        return None
    lead, whole, dec, trail = m.groups()
    dec = (dec or "")
    scale = unit_scale(unit)
    # value in units = whole.dec ; cents = units * scale
    num = int(whole.replace(".", "")) * scale
    if dec:
        num += int(dec) * scale // (10 ** len(dec))
    neg = lead == "-" or trail == "-" or (s.startswith("(") and s.endswith(")"))
    return -num if neg else num


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def doc_id_of(path: Path, doc: dict | None = None) -> str:
    if doc and doc.get("meta", {}).get("doc_id"):
        return doc["meta"]["doc_id"]
    return Path(path).name.removesuffix(".json").removesuffix(".key").removesuffix(".pred")


def iter_predictions(pred_dir: Path):
    """Yield (doc_id, path) for every output JSON under pred_dir (<doc_id>.pred.json, .json or .key.json)."""
    for p in sorted(Path(pred_dir).rglob("*.json")):
        if any(part.startswith(("_", ".")) for part in p.relative_to(pred_dir).parts):
            continue  # _eval reports, _generator, hidden folders
        yield doc_id_of(p), p


class Corpus:
    """Finds the answer key and the source document of a doc_id."""

    def __init__(self, root: Path = DEFAULT_CORPUS):
        self.root = Path(root)
        self.keys = {p.name.removesuffix(".key.json"): p for p in self.root.rglob("*.key.json")
                     if not any(s.startswith("_") for s in p.relative_to(self.root).parts)}

    def key(self, doc_id: str) -> dict | None:
        p = self.keys.get(doc_id)
        return load(p) if p else None

    def source(self, doc_id: str) -> Path | None:
        k = self.keys.get(doc_id)
        folder = k.parent if k else self.root
        for ext in (".pdf", ".xlsx"):
            hits = list(folder.glob(doc_id + ext)) or list(self.root.rglob(doc_id + ext))
            if hits:
                return hits[0]
        return None


def row_label(r: dict) -> str:
    ident = r.get("asset_no") or r.get("account") or r.get("class") or r.get("position") or r.get("name") or ""
    sub = f"/{r['sub_no']}" if r.get("sub_no") not in (None, "", "0") else ""
    return f"{r.get('year')} {r.get('kind')} {ident}{sub}".strip()


def where(r: dict) -> str:
    p = r.get("pointer") or {}
    if "sheet" in p:
        return f"{p['sheet']}!{p.get('cell', '?')}"
    if "page" in p:
        return f"p{p['page']} l{p.get('line', '?')}"
    return "no pointer"


def is_flagged(r: dict, field: str | None = None) -> bool:
    fl = r.get("flags") or {}
    return bool(fl) if field is None else (field in fl or "*" in fl)


def numeric(fields: dict, f: str):
    v = fields.get(f)
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def law_residuals(r: dict, unit: str):
    """Yield (target, terms, diff, tol) for every law whose fields the row prints (blanks skip the law)."""
    f = r.get("fields") or {}
    for target, terms, optional in LAWS:
        if numeric(f, target) is None:
            continue
        needed = [t for t in terms if t not in optional]
        if not all(numeric(f, t) is not None for t in needed):
            continue
        if any(t in f and numeric(f, t) is None for t in terms):  # an optional term left blank
            continue
        diff = f[target] - sum(s * (numeric(f, t) or 0) for t, s in terms.items())
        yield target, terms, diff, tolerance(unit, len(terms) + 1)


def kids_of(rows: list[dict], i: int) -> list[dict]:
    """Asset rows a total row sums up (same rule as the generator's checker)."""
    r = rows[i]
    return [a for j, a in enumerate(rows) if a.get("kind") == "asset" and a.get("year") == r.get("year")
            and all(a.get(k) == r[k] for k in ("class", "account", "position") if r.get(k))
            and (r["kind"] != "carry_over" or j < i)]


# ---------------------------------------------------------------------------- pointer geometry

def overlap_ratio(inner, outer) -> float:
    """Share of `inner`'s area that lies inside `outer` (boxes are [x0, y0, x1, y1])."""
    if not inner or not outer:
        return 0.0
    ix0, iy0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix1, iy1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    area = max((inner[2] - inner[0]) * (inner[3] - inner[1]), 1e-9)
    return (ix1 - ix0) * (iy1 - iy0) / area


def field_box(r: dict, f: str):
    """PDF box of one value: its own `pointers` entry if given, else the row's bbox."""
    return ((r.get("pointers") or {}).get(f) or {}).get("bbox") or (r.get("pointer") or {}).get("bbox")


def field_page(r: dict, f: str):
    return ((r.get("pointers") or {}).get(f) or {}).get("page") or (r.get("pointer") or {}).get("page")


def field_cell(r: dict, f: str) -> tuple[str | None, str | None]:
    """(sheet, cell) of one value: its own `pointers` entry if given, else pointer.cells[field]."""
    own = (r.get("pointers") or {}).get(f) or {}
    p = r.get("pointer") or {}
    if own.get("cell"):
        return own.get("sheet", p.get("sheet")), own["cell"]
    return p.get("sheet"), (p.get("cells") or {}).get(f)


@functools.lru_cache(maxsize=4)  # the pointer and completeness checks read the same document
def pdf_words(path: Path) -> list[list[tuple]]:
    """Words of every page as (x0, top, x1, bottom, text), in the keys' coordinates (points, top-left origin).
    Same pdfplumber reading as carth/ingest/pdf_text.py: doubled fake-bold glyphs removed, turned pages read
    bottom-to-top."""
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            ws = page.dedupe_chars(tolerance=1).extract_words(keep_blank_chars=False, use_text_flow=False,
                                                              line_dir_rotated="ltr", char_dir_rotated="btt")
            pages.append([(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in ws])
    return pages


def centre_in(w, box, pad: float = 1.0) -> bool:
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    return box[0] - pad <= cx <= box[2] + pad and box[1] - pad <= cy <= box[3] + pad


# ---------------------------------------------------------------------------- row matching

def _similarity(k: dict, p: dict) -> float:
    s = 0.0
    if k.get("asset_no") and p.get("asset_no"):
        s += 5 if str(k["asset_no"]) == str(p["asset_no"]) else -5
        if k.get("sub_no") not in (None, "") and str(k.get("sub_no")) == str(p.get("sub_no") or ""):
            s += 1
    for f in ("class", "account", "position", "level"):
        if k.get(f) and p.get(f):
            s += 1 if str(k[f]) == str(p[f]) else -1
    kp, pp = k.get("pointer") or {}, p.get("pointer") or {}
    if "sheet" in kp and kp.get("sheet") == pp.get("sheet") and kp.get("cell") == pp.get("cell"):
        s += 3
    elif "page" in kp and kp.get("page") == pp.get("page"):
        if kp.get("line") is not None and kp.get("line") == pp.get("line"):
            s += 3
        elif overlap_ratio(pp.get("bbox"), kp.get("bbox")) > 0.5:
            s += 2
    kf, pf = k.get("fields") or {}, p.get("fields") or {}
    if kf:
        s += 3 * sum(1 for f, v in kf.items() if pf.get(f) == v) / len(kf)
    return s


def match_rows(key_rows: list[dict], pred_rows: list[dict], min_score: float = 3.0):
    """Pair each key row with at most one predicted row of the same year and kind, best similarity first.
    Returns (pairs [(key_index, pred_index | None)], unmatched pred indices)."""
    cands = []
    for ki, k in enumerate(key_rows):
        for pi, p in enumerate(pred_rows):
            if k.get("year") == p.get("year") and k.get("kind") == p.get("kind"):
                sc = _similarity(k, p)
                if sc >= min_score:
                    cands.append((sc, ki, pi))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))
    k2p, used = {}, set()
    for sc, ki, pi in cands:
        if ki not in k2p and pi not in used:
            k2p[ki] = pi
            used.add(pi)
    pairs = [(ki, k2p.get(ki)) for ki in range(len(key_rows))]
    return pairs, [pi for pi in range(len(pred_rows)) if pi not in used]


def issue(check: str, severity: str, message: str, row: dict | None = None, field: str | None = None, **extra):
    d = {"check": check, "severity": severity, "message": message}
    if row is not None:
        d["row"] = row_label(row)
        d["where"] = where(row)
    if field:
        d["field"] = field
    d.update(extra)
    return d
