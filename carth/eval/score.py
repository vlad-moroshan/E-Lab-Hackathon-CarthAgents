"""Local heuristic reference benchmark (+1 supported observed value, 0 blank, -3 unsupported/wrong).

PDF boxes must surround source tokens with at most two points of padding per side and stay on the page.
Field positions are learned from other records in the same page/geometry section. Unknown, ambiguous and clipped
references earn no credit. Workbook references read the source literal/cache, preserving signed transfers; conflicts
with fixture truth use the observed cell value. Identity includes year, role and printed asset/class/account/position.
Neither learned positions nor OCR tokens are independent visual ground truth. This is not the official scorer.

Accepts fixture rows with local per-value pointers, or the extraction values/rows contract. Net fields use net:<name>.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from carth import ingest
from carth.eval.evidence import Ref, pdf_refs, targets, xlsx_refs
from carth.eval.frames import turn_box
from carth.ingest.pdf_text import pdf_tokens

WRONG, RIGHT = -3, 1


@dataclass
class DocScore:
    doc_id: str
    family: str
    format: str
    variant: str
    total: int = 0  # scored key values (standard + net)
    net_total: int = 0
    unshown: int = 0  # key values the document does not show (ref kind "none"): only a blank is safe
    right: int = 0
    wrong: int = 0
    blank: int = 0
    extra: int = 0
    loose_right: int = 0  # right, but column not verified (ref "multi") or geometry only (ref "weak")
    conflicts: int = 0  # source-cell amounts contradicting fixture key truth
    errors: list = field(default_factory=list)

    @property
    def score(self) -> int:
        return RIGHT * self.right + WRONG * (self.wrong + self.extra)


def load_keys(corpus: Path) -> dict[str, tuple[Path, dict]]:
    out = {}
    for p in sorted(corpus.rglob("*.key.json")):
        if any(s.startswith(("_", ".")) for s in p.relative_to(corpus).parts):
            continue
        k = json.loads(p.read_text("utf-8"))
        out[k["meta"]["doc_id"]] = (p, k)
    return out


def _doc_path(key_path: Path, key: dict) -> Path:
    return key_path.with_name(key["meta"]["doc_id"] + (".xlsx" if key["meta"]["format"] == "xlsx" else ".pdf"))


def build_refs(key_path: Path, key: dict, ref_tokens: Path | None = None) -> tuple[dict, dict, dict]:
    """(refs, turns, page_sizes) for a key's document. Cached per process."""
    doc = _doc_path(key_path, key)
    tp = ref_tokens / f"{key['meta']['doc_id']}.json" if ref_tokens else None
    ck = (str(key_path), json.dumps(key, sort_keys=True), doc.stat().st_mtime_ns,
          str(ref_tokens), tp.stat().st_mtime_ns if tp and tp.exists() else None)
    if ck in _CACHE:
        out, required = _CACHE[ck]
        _REQUIRED[(str(key_path), json.dumps(key, sort_keys=True))] = required
        return out
    if key["meta"]["format"] == "xlsx":
        toks = ingest.ingest(doc)["tokens"]
        out = (xlsx_refs(key, doc, toks), {}, {})
    else:
        with pdfplumber.open(doc) as pdf:
            sizes = {p.page_number: (float(p.width), float(p.height)) for p in pdf.pages}
            text = any(p.chars for p in pdf.pages)
        toks = pdf_tokens(doc) if text else None
        if not text and ref_tokens and (ref_tokens / f"{key['meta']['doc_id']}.json").exists():
            toks = ingest.load(ref_tokens / f"{key['meta']['doc_id']}.json")["tokens"]
        refs, turns = pdf_refs(key, toks, sizes, text)
        out = (refs, turns, sizes)
    # Fixture identities can include unprinted generator classifications. Never require these in runtime output.
    printed = {word for t in toks or [] if t.get("kind", "text") == "text"
               for word in [t["text"], *re.findall(r"[\w.]+", t["text"])]}
    _REQUIRED[(str(key_path), json.dumps(key, sort_keys=True))] = {
        i: {"year", "kind", "asset_no", "sub_no"} | {f for f in ("class", "account", "position")
             if str(r.get(f)) in printed} for i, r in enumerate(key["rows"])}
    _CACHE[ck] = (out, _REQUIRED[(str(key_path), json.dumps(key, sort_keys=True))])
    return out


_CACHE: dict = {}
_REQUIRED: dict = {}


def _pointer(prow: dict, f: str) -> dict | None:
    if f in prow.get("pointers", {}):
        p = prow["pointers"][f]
        return p if isinstance(p, dict) else None
    p = prow.get("pointer")
    if not isinstance(p, dict) or not p or f.startswith("net:"):
        return None
    if "sheet" in p:
        return {"sheet": p["sheet"], "cell": p.get("cells", {}).get(f, p.get("cell"))}
    return {"page": p.get("page"), "bbox": p.get("bbox")}


def _accepts(ref: Ref, ptr: dict, row_bbox) -> bool:
    if not isinstance(ptr, dict):
        return False
    if ref.kind in ("cell", "blank_cell"):
        return ptr.get("sheet") == ref.sheet and ptr.get("cell") == ref.cell
    if ref.kind not in ("token", "blank") or "bbox" not in ptr or ptr.get("page") != ref.page:
        return False
    b = ptr["bbox"]
    if not valid_box(b):
        return False
    w, h = b[2] - b[0], b[3] - b[1]
    for rb in ref.alts or [ref.bbox]:
        rw, rh = rb[2] - rb[0], rb[3] - rb[1]
        # Rounding slack only. A pointer must surround all source characters.
        covers = b[0] <= rb[0] + .02 and b[1] <= rb[1] + .02 and b[2] >= rb[2] - .02 and b[3] >= rb[3] - .02
        padded = b[0] >= rb[0] - 2.01 and b[1] >= rb[1] - 2.01 and b[2] <= rb[2] + 2.01 and b[3] <= rb[3] + 2.01
        if covers and padded and w <= rw + 4.01 and h <= rh + 4.01:
            return True
    return False


def valid_box(b, size=None) -> bool:
    return (isinstance(b, (list, tuple)) and len(b) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in b)
            and 0 <= b[0] < b[2] and 0 <= b[1] < b[3]
            and (size is None or (b[2] <= size[0] + .02 and b[3] <= size[1] + .02)))


def _identity_ok(prow: dict, krow: dict, required: set | None = None) -> bool:
    if krow.get("level") and prow.get("level", prow.get("granularity")) != krow["level"]:
        return False
    for name in ("year", "kind", "asset_no", "sub_no", "class", "account", "position"):
        if krow.get(name) not in (None, ""):
            if required is not None and name not in required and prow.get(name) in (None, ""):
                continue
            if str(prow.get(name)) != str(krow[name]):
                return False
        elif prow.get(name) not in (None, ""):
            return False
    return True


def score_doc(key_path: Path, key: dict, pred: dict | None, ref_tokens: Path | None = None) -> DocScore:
    if pred and "values" in pred:
        rows = {r["id"]: {**r, "fields": {}, "pointers": {}} for r in pred["rows"]}
        expanded = []
        for v in pred["values"]:
            row = rows.get(v["row"], {})
            # Keep each record separate so duplicate values still incur penalties.
            expanded.append({**row, "fields": {v["field"]: v["value"]}, "pointers": {v["field"]: v["pointer"]}})
        pred = {"rows": expanded}
    m = key["meta"]
    ds = DocScore(m["doc_id"], m["family"], m["format"], m["variant"])
    refs, turns, sizes = build_refs(key_path, key, ref_tokens)
    required = _REQUIRED.get((str(key_path), json.dumps(key, sort_keys=True)), {})
    tg = {(i, f): v for i, f, v in targets(key)}
    ds.total, ds.net_total = len(tg), sum(f.startswith("net:") for _, f in tg)
    ds.unshown = sum(r.kind == "none" for r in refs.values())
    ds.conflicts = sum(r.observed is not None and r.observed != tg[target] for target, r in refs.items())
    by_field = defaultdict(list)
    for (i, f) in tg:
        by_field[f].append(i)

    def err(**kw):
        if len(ds.errors) < 8:
            ds.errors.append(kw)

    seen: dict[tuple, int] = {}
    source_seen = set()
    for prow in (pred or {}).get("rows", []):
        vals = list(prow.get("fields", {}).items()) + [(f"net:{k}", v) for k, v in prow.get("net_fields", {}).items()]
        for f, v in vals:
            if v is None:
                continue  # flagged blank
            ptr = _pointer(prow, f)
            if ptr and "bbox" in ptr and not valid_box(ptr["bbox"], sizes.get(ptr.get("page"), (0, 0))):
                ptr = None
            if ptr and "bbox" in ptr and turns.get(ptr.get("page")):  # scans: our page-as-given box -> key frame
                W, H = sizes[ptr["page"]]
                ptr = {**ptr, "bbox": turn_box(ptr["bbox"], turns[ptr["page"]], W, H)}
            cands = [i for i in by_field.get(f, []) if ptr
                     and _accepts(refs[(i, f)], ptr, key["rows"][i]["pointer"].get("bbox"))]
            if len(cands) > 1:  # e.g. a box over two rows: prefer the row the prediction says it is
                cands = [i for i in cands if _identity_ok(prow, key["rows"][i], required.get(i))] or cands
            if len(cands) != 1 or (cands[0], f) in seen:
                ds.extra += 1
                err(extra=f, value=v, pointer=ptr, why="no unique target" if len(cands) != 1 else "duplicate")
                continue
            i = cands[0]
            krow, ref = key["rows"][i], refs[(i, f)]
            occurrence = ((ref.sheet, ref.cell) if ref.cell else (ref.page, tuple(ref.bbox)))
            if occurrence in source_seen:
                ds.extra += 1
                err(extra=f, why="source occurrence already used")
                continue
            source_seen.add(occurrence)
            expected = ref.observed if ref.observed is not None else tg[(i, f)]
            ok = isinstance(v, int) and not isinstance(v, bool) and v == expected and _identity_ok(prow, krow, required.get(i))
            seen[(i, f)] = RIGHT if ok else WRONG
            if ok and ref.kind in ("weak", "multi"):
                ds.loose_right += 1
            if not ok:
                err(row=i, field=f, pred=v, key=tg[(i, f)], year=(prow.get("year"), krow.get("year")),
                    asset=(prow.get("asset_no"), krow.get("asset_no")))
    ds.right = sum(1 for s in seen.values() if s == RIGHT)
    ds.wrong = sum(1 for s in seen.values() if s == WRONG)
    ds.blank = ds.total - len(seen)
    return ds


def score_corpus(corpus: Path, pred_dir: Path, only: set[str] | None = None,
                 ref_tokens: Path | None = None) -> list[DocScore]:
    out = []
    for doc_id, (kp, key) in load_keys(corpus).items():
        if only and key["meta"]["format"] not in only:
            continue
        pp = pred_dir / f"{doc_id}.pred.json"
        pred = json.loads(pp.read_text("utf-8")) if pp.exists() else None
        out.append(score_doc(kp, key, pred, ref_tokens))
    return out


def report(scores: list[DocScore], verbose: bool = False) -> str:
    cols = ("right", "wrong", "blank", "extra", "loose_right", "unshown", "net_total", "conflicts")

    def agg(name, ss):
        t = sum(s.total for s in ss)
        sc = sum(s.score for s in ss)
        pct = 100 * sc / t if t else 0
        return f"{name:<28}{len(ss):>4}{t:>7}{sc:>8}{pct:>7.1f}%" + "".join(
            f"{sum(getattr(s, c) for s in ss):>8}" for c in cols)

    head = f"{'group':<28}{'docs':>4}{'vals':>7}{'score':>8}{'pct':>8}" + "".join(f"{c[:7]:>8}" for c in cols)
    lines = [head, "-" * len(head)]
    for key in ("family", "format", "variant"):
        groups = defaultdict(list)
        for s in scores:
            groups[getattr(s, key)].append(s)
        lines += [agg(f"{key}={g}", ss) for g, ss in sorted(groups.items())] + [""]
    lines.append(agg("TOTAL", scores))
    lines.append("Heuristic reference benchmark, not an official score or evidence ceiling. Weak/multi references earn no credit; "
                 "source/key conflicts use the observed cell value. OCR references are not independently pixel-verified.")
    if verbose:
        lines.append("")
        for s in scores:
            lines.append(agg(s.doc_id, [s]))
            lines += [f"    {e}" for e in s.errors[:3]]
    return "\n".join(lines)


def oracle_pred(key: dict, mode: str = "key", key_path: Path | None = None, ref_tokens: Path | None = None) -> dict:
    """'key': the answer key as is (row-level PDF boxes: NOT value-level evidence, fails on PDFs by design).
    'empty': no rows (scores 0). 'evidence': key values with value-level pointers to their references, blanks where
    evidence is unresolved; a conservative reference-generated benchmark, not a ceiling."""
    if mode == "empty":
        return {**key, "rows": [], "planted": []}
    if mode == "key":
        return key
    refs, turns, sizes = build_refs(key_path, key, ref_tokens)
    rows = []
    used = set()
    for i, r in enumerate(key["rows"]):
        row = {k: v for k, v in r.items() if k not in ("fields", "net_fields", "pointer", "printed", "flags")}
        row["fields"], row["net_fields"], row["pointers"] = {}, {}, {}
        for f, v in [*r.get("fields", {}).items(), *[(f"net:{k}", x) for k, x in r.get("net_fields", {}).items()]]:
            ref = refs[(i, f)]
            occurrence = (ref.sheet, ref.cell) if ref.cell else (ref.page, tuple(ref.bbox or []))
            ok = ref.kind in ("token", "blank", "cell", "blank_cell") and occurrence not in used
            if ok:
                used.add(occurrence)
            (row["net_fields"] if f.startswith("net:") else row["fields"])[f.removeprefix("net:")] = (ref.observed if ref.observed is not None else v) if ok else None
            if ok and (ref.kind in ("cell", "blank_cell") or ref.cells):
                row["pointers"][f] = {"sheet": ref.sheet, "cell": ref.cells[0] if ref.cells else ref.cell}
            elif ok:
                bbox = ref.alts[0] if ref.alts else ref.bbox
                if turns.get(ref.page):  # back from the key frame to the page as given
                    W, H = sizes[ref.page]
                    t = turns[ref.page]
                    bbox = turn_box(bbox, (360 - t) % 360, *((H, W) if t in (90, 270) else (W, H)))
                row["pointers"][f] = {"page": ref.page, "bbox": bbox}
        row["pointer"] = r["pointer"]
        rows.append(row)
    result = {"meta": key["meta"], "rows": rows, "planted": key.get("planted", [])}
    # Ambiguous source occurrences must not become oracle extras.
    for row in rows:
        for f, ptr in list(row["pointers"].items()):
            checked = ptr
            if "bbox" in ptr and turns.get(ptr["page"]):
                checked = {**ptr, "bbox": turn_box(ptr["bbox"], turns[ptr["page"]], *sizes[ptr["page"]])}
            matches = [i for i, k in enumerate(key["rows"]) if (i, f) in refs
                       and _identity_ok(row, k) and _accepts(refs[(i, f)],
                           checked, k["pointer"].get("bbox"))]
            if len(matches) != 1:
                (row["net_fields"] if f.startswith("net:") else row["fields"])[f.removeprefix("net:")] = None
                del row["pointers"][f]
    return result
