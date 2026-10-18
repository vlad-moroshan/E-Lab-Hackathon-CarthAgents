"""Stage 4 (M7): layout (M5) + LLM spec (M6) -> per-row source references, the input of carth.output.extract.

For every section of the spec, its pages' lines (or sheet rows) are walked in order:
  * a line matching the section's `record_start` regex opens a record; the next `record_lines - 1` lines join it
    (a new start closes it early). Repeated page headers / noise lines (roles "header", "noise") never start one.
  * the record's role comes from the `roles` regexes on its first line: subtotal / total / carry-over / heading
    (headings carry no values), otherwise a leaf ("asset" kind at the section's granularity).
  * every field map (line offset, band) -> field picks the token in that band on that line of the record, or for
    xlsx the cell in that column; nothing is guessed: a missing token stays a blank with a reason.
Regexes are applied to the same masked line text the model saw (carth.spec), with and without the "L12 g… i…:"
prefix. Identity: year from the section, asset_no from the section's regex on the first line, name = its text
words. A leaf asset row whose asset_no cannot be found gets only blanks: a value on an unidentified row is a −3 risk.

    python -m carth.resolve A3-Hackathon-Corpus --out out/m7 [--types pdf,xlsx] [--docs stem,…] [--workers 8]
writes out/m7/<stem>.layout.json (references), <stem>.json + .xlsx (carth.output) and pred/<stem>.pred.json
(the local scorer's format) for `carth eval --pred out/m7/pred`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from openpyxl.utils import get_column_letter

from carth.spec import _cell

NET = {"bew_ahk": "net:bew_ahk", "bew_wb": "net:bew_wb"}


def _rx(pattern: str | None):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.I)
    except re.error:
        return None


def _texts(v: dict) -> tuple:
    return v["plain"], v["body"], v["full"]


def _match(rx, v: dict) -> bool:
    return bool(rx and any(rx.search(t) for t in _texts(v)))


def _search(rx, v: dict):
    return next((m for t in _texts(v) if (m := rx.search(t))), None) if rx else None


def _views(lay: dict) -> list[dict]:
    """Every line in reading order with its masked body / full view text and its cells."""
    toks, out = lay["tokens"], []
    if lay["kind"] == "xlsx":
        for sh in lay["sheets"]:
            for ln in sh["lines"]:
                body = " | ".join(f"{toks[c['tid']]['cell']}={_cell(toks[c['tid']], c['band'], True)}" for c in ln["cells"])
                plain = " | ".join(re.sub(r"#(-?)c\d+", r"#\1", _cell(toks[c["tid"]], c["band"], True)) for c in ln["cells"])
                out.append({"page": None, "sheet": sh["sheet"], "row": ln["row"], "id": ln["id"], "cells": ln["cells"],
                            "body": body, "plain": plain,
                            "full": f"R{ln['row']}{' [hidden]' if ln['hidden'] else ''}: {body}"})
        return out
    for pg in lay["pages"]:
        for ln in pg["lines"]:
            body = " ".join(_cell(toks[c["tid"]], c["band"], False) for c in ln["cells"])
            gap = "" if ln["gap_above"] is None else f" g{ln['gap_above']:.1f}"
            out.append({"page": pg["page"], "sheet": None, "id": ln["id"], "cells": ln["cells"], "body": body,
                        "plain": re.sub(r"@b\d+|#(-?)b[\d?]+", lambda m: f"#{m.group(1) or ''}" if m.group(0).startswith("#") else "", body),
                        "full": f"L{ln['id'].split('l')[-1]}{gap} i{ln['indent']:.0f}: {body}"})
    return out


def _section_of(spec, view: dict):
    """Section owning a line: by sheet, by listed page, else the section of the nearest earlier listed page."""
    if view["sheet"] is not None:
        return next((s for s in spec.sections if s.sheet == view["sheet"]), None)
    for s in spec.sections:
        if view["page"] in s.pages:
            return s
    earlier = [(max(p for p in s.pages if p <= view["page"]), s) for s in spec.sections
               if any(p <= view["page"] for p in s.pages)]
    return max(earlier, key=lambda x: x[0])[1] if earlier else None


PERIOD = re.compile(r"(?:zum|bis|per|Stichtag|Berichtsdatum:?|Jahresabschluss per)\s*\d{1,2}\.\d{1,2}\.(\d{4})", re.I)
LEVEL_IDS = {"class_subtotal": {"class"}, "account_subtotal": {"account"}, "position_subtotal": {"position"},
             "grand_total": set(), "carry_over": {"class", "account", "position"}}


def _fallback_year(views: list[dict]) -> int | None:
    """Fiscal year from printed period phrases ("… zum 31.12.2025", "bis 30.06.2025"); the most common wins."""
    years = Counter(int(y) for v in views for y in PERIOD.findall(v["body"]))
    return years.most_common(1)[0][0] if years else None


def _code(m) -> str | None:
    if not m:
        return None
    s = (m.group(1) if m.groups() else m.group(0)).strip()
    return re.sub(r"@b\d+$|^[A-Z]+\d+=", "", s) or None


def resolve(doc: dict, lay: dict, spec) -> dict:
    """References in the carth.output layout-spec format: {"sha256", "unit", "rows": [...]}."""
    toks = lay["tokens"]
    units = [s.unit for s in spec.sections] or ["EUR"]
    out = {"sha256": doc["sha256"], "unit": max(set(units), key=units.count), "rows": [], "notes": []}
    if not spec.is_asset_schedule:
        out["notes"].append("not an asset schedule: no rows")
        return out
    views = [v for v in _views(lay) if v["page"] not in set(spec.noise_pages)]
    compiled = {id(s): (_rx(s.record_start), [(_rx(r.regex), r.role) for r in s.roles],
                        [(_rx(i.regex), i.field, i.scope) for i in s.ids]) for s in spec.sections}
    fallback = _fallback_year(_views(lay))
    records, cur = [], None
    context: dict = {}  # codes from heading lines, per section, carried down to the rows below
    for v in views:
        s = _section_of(spec, v)
        if s is None:
            continue
        start, roles, ids = compiled[id(s)]
        role = next((r for rx, r in roles if _match(rx, v)), None)
        if role in ("header", "noise"):
            continue
        ctx = context.setdefault(id(s), {})
        for rx, field, scope in ids:  # a heading code applies to everything below it
            if scope == "heading" and rx:
                code = _code(_search(rx, v))
                if code:
                    ctx[field] = code
        if _match(start, v):
            cur = {"section": s, "lines": [v], "role": role, "context": dict(ctx)}
            records.append(cur)
        elif cur is not None and cur["section"] is s and len(cur["lines"]) < s.record_lines:
            cur["lines"].append(v)
        else:
            cur = None
    for k, rec in enumerate(records):
        s, first = rec["section"], rec["lines"][0]
        role = rec["role"]
        if role == "heading":
            continue
        kind = role if role in ("class_subtotal", "account_subtotal", "position_subtotal", "grand_total",
                                "carry_over") else "asset"
        _, _, ids = compiled[id(s)]
        ident = dict(rec["context"])
        for rx, field, scope in ids:
            if scope == "record" and rx:
                code = _code(_search(rx, first))
                if code:
                    ident[field] = code
        if kind != "asset":  # a sum line carries only its own level's code; no asset numbers
            ident = {f: c for f, c in ident.items() if f in LEVEL_IDS[kind]}
        asset_no = ident.get("asset_no")
        year = s.year or fallback
        name = " ".join(toks[c["tid"]]["text"] for c in first["cells"] if c["type"] == "text") or None
        row = {"id": f"r{k}:{first['id']}", "year": year or 1900, "kind": kind, "granularity": s.granularity,
               "asset_no": asset_no, "sub_no": ident.get("sub_no"), "class": ident.get("class"),
               "account": ident.get("account"), "position": ident.get("position"), "name": name, "fields": {}}
        unidentified = (kind == "asset" and s.granularity == "asset" and not asset_no) or not year
        for fm in s.fields:
            if fm.field == "ignore":
                continue
            field = NET.get(fm.field, fm.field)
            if field in row["fields"]:
                continue
            if unidentified:
                row["fields"][field] = {"amount_column": True, "blank_reason": "row identity unresolved"}
                continue
            if fm.line >= len(rec["lines"]):
                row["fields"][field] = {"amount_column": True, "blank_reason": "record line not found"}
                continue
            ln = rec["lines"][fm.line]
            if ln["sheet"] is not None:
                row["fields"][field] = {"sheet": ln["sheet"], "cell": f"{get_column_letter(fm.band)}{ln['row']}",
                                        "amount_column": True}
                continue
            cell = next((c for c in ln["cells"] if c["band"] == fm.band and c["type"] in ("amount", "int")), None)
            row["fields"][field] = ({"token": cell["tid"], "amount_column": True} if cell else
                                    {"amount_column": True, "blank_reason": "no amount in this column (empty cell in a "
                                                                            "PDF: no evidence box yet)"})
        if row["fields"]:
            out["rows"].append(row)
    return out


def to_pred(result: dict) -> dict:
    """carth.output result -> key-style JSON: rows with `fields`, `printed` (the raw source text), a row `pointer`
    (PDF: page + the union box of the row's value tokens; xlsx: sheet, anchor cell, per-field `cells`) as the
    organisers' check_corpus expects, plus per-value `pointers` for the local strict scorer."""
    rows = {}
    for r in result["rows"]:
        rows[r["id"]] = {k: r.get(k) for k in ("kind", "year", "asset_no", "sub_no", "class", "account", "position",
                                                "name")} | {"fields": {}, "net_fields": {}, "printed": {},
                                                            "pointers": {}, "pointer": None}
    for v in result["values"]:
        row, f, p = rows[v["row"]], v["field"], v["pointer"]
        if v["value"] is None or not p:
            continue
        (row["net_fields"] if f.startswith("net:") else row["fields"])[f.removeprefix("net:")] = v["value"]
        if not f.startswith("net:"):
            row["printed"][f] = (v["trace"] or {}).get("raw") or ""
        row["pointers"][f] = p
        rp = row["pointer"]
        if "sheet" in p:
            row["pointer"] = rp or {"sheet": p["sheet"], "cell": p["cell"], "cells": {}}
            if not f.startswith("net:"):
                row["pointer"]["cells"][f] = p["cell"]
        elif rp is None:
            row["pointer"] = {"page": p["page"], "line": 0, "bbox": list(p["bbox"])}
        elif rp["page"] == p["page"]:
            b = rp["bbox"]
            rp["bbox"] = [min(b[0], p["bbox"][0]), min(b[1], p["bbox"][1]), max(b[2], p["bbox"][2]), max(b[3], p["bbox"][3])]
    keep = [r for r in rows.values() if r["pointer"]]
    years = sorted({r["year"] for r in keep})
    return {"meta": {"doc_id": result["document"]["id"], "years": years}, "rows": keep, "planted": []}


def _one(path: Path, out: Path, model: str | None) -> str:
    from carth import ingest, output
    from carth.layout import layout
    from carth.spec import DEFAULT_MODEL, infer

    doc = ingest.ingest(path)
    lay = layout(doc)
    spec, info = infer(lay, model or DEFAULT_MODEL)
    refs = resolve(doc, lay, spec)
    (out / f"{path.stem}.layout.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), "utf-8")
    result = output.extract(doc, refs, path.stem)
    output.write_outputs(result, out)
    (out / "pred").mkdir(parents=True, exist_ok=True)
    (out / "pred" / f"{path.stem}.pred.json").write_text(json.dumps(to_pred(result), ensure_ascii=False), "utf-8")
    vals = [v for v in result["values"] if v["value"] is not None]
    return (f"{path.stem:<28} rows {len(result['rows']):>4} values {len(vals):>5} blanks "
            f"{len(result['values']) - len(vals):>5} spec {info['seconds']:>5.1f}s{' cached' if info.get('cached') else ''}")


def main() -> None:
    import argparse
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from carth import ingest

    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/m7"))
    ap.add_argument("--types", default="pdf,xlsx")
    ap.add_argument("--docs")
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    types = {"." + t for t in a.types.split(",")}
    only = set(a.docs.split(",")) if a.docs else None
    paths = [p for p in ingest.find_documents(a.input) if p.suffix.lower() in types and (not only or p.stem in only)]
    with ThreadPoolExecutor(a.workers) as pool:  # the LLM call dominates: threads are enough
        futs = {pool.submit(_one, p, a.out, a.model): p for p in paths}
        for f in as_completed(futs):
            try:
                print(f.result(), flush=True)
            except Exception as e:  # one document must not stop the batch
                print(f"{futs[f].stem:<28} FAILED {type(e).__name__}: {str(e)[:160]}", flush=True)


if __name__ == "__main__":
    main()
