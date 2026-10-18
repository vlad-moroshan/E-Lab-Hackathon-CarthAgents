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
from carth.sections import section_views

NET = {"bew_ahk": "net:bew_ahk", "bew_wb": "net:bew_wb"}


def _rx(pattern: str | None):
    if not pattern:
        return None
    return re.compile(pattern, re.I)


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
                        "frame": ln.get("frame", "page"),
                        "plain": re.sub(r"@b\d+|#(-?)b[\d?]+", lambda m: f"#{m.group(1) or ''}" if m.group(0).startswith("#") else "", body),
                        "full": f"L{ln['id'].split('l')[-1]}{gap} i{ln['indent']:.0f}: {body}"})
    return out




PERIOD = re.compile(r"(?:zum|bis|per|Stichtag|Berichtsdatum:?|Jahresabschluss per)\s*\d{1,2}\.\d{1,2}\.(\d{4})", re.I)
LEVEL_IDS = {"class_subtotal": {"class"}, "account_subtotal": {"account"}, "position_subtotal": {"position"},
             "grand_total": set(), "carry_over": {"class", "account", "position"}}


def _fallback_year(views: list[dict]) -> int | None:
    """A unique fiscal year from period phrases inside the owning section only."""
    years = {int(y) for v in views for y in PERIOD.findall(v["body"])}
    return next(iter(years)) if len(years) == 1 else None


def _code(m) -> str | None:
    if not m:
        return None
    s = (m.group(1) if m.groups() else m.group(0)).strip()
    return re.sub(r"@b\d+$|^[A-Z]+\d+=", "", s) or None


def validate_references(doc, lay, spec):
    """Check model references against the actual source before selecting any amount."""
    pages = {p['page'] for p in lay.get('pages', [])}
    sheets = {s['sheet']:s for s in doc.get('sheets', [])}
    if any(p not in pages for p in spec.noise_pages):
        raise ValueError('unknown noise page')
    for s in spec.sections:
        if lay['kind'] == 'xlsx':
            if s.sheet not in sheets or s.pages:
                raise ValueError(f'{s.name}: unknown sheet or PDF pages in workbook section')
            for field in s.fields:
                if not 1 <= field.band <= sheets[s.sheet]['max_col']:
                    raise ValueError(f'{s.name}: invalid workbook column {field.band}')
        elif s.sheet is not None or not s.pages or set(s.pages) - pages:
            raise ValueError(f'{s.name}: invalid PDF page selection')
        if set(s.pages) & set(spec.noise_pages):
            raise ValueError(f'{s.name}: section includes noise pages')


def _unglue(code: str, view: dict, toks: dict) -> tuple[str, str | None]:
    """An id printed glued to its description ("143Bürostuhl", "91aFabrikhalle") is captured with a stray letter.
    Only when the source token really continues past the code: digits are the id, a single lowercase letter right
    before the (capitalised) description is the sub-number."""
    m = re.match(r"^(\d+)([a-z]?)[A-ZÄÖÜ]?$", code)
    if not m:
        return code, None
    glued = any(toks[c["tid"]]["text"].startswith(m.group(1)) and len(toks[c["tid"]]["text"]) > len(code)
                for c in view["cells"])
    return (m.group(1), m.group(2) or None) if glued else (code, None)


def resolve(doc: dict, lay: dict, spec) -> dict:
    """References in the carth.output layout-spec format: {"sha256", "unit", "rows": [...]}."""
    toks = lay["tokens"]
    units = {s.unit for s in spec.sections}
    out = {"sha256": doc["sha256"], "unit": next(iter(units)) if len(units) == 1 else None,
           "rows": [], "notes": []}
    if not spec.is_asset_schedule:
        out["notes"].append("not an asset schedule: no rows")
        return out
    validate_references(doc, lay, spec)
    views = [v for v in _views(lay) if v["page"] not in set(spec.noise_pages)]
    compiled = {id(s): (_rx(s.record_start), [(_rx(r.regex), r.role) for r in s.roles],
                        [(_rx(i.regex), i.field, i.scope) for i in s.ids]) for s in spec.sections}
    owned = section_views(spec, views)
    if lay['kind'] != 'xlsx':
        for s in spec.sections:
            frames = {v.get('frame', 'page') for v in owned[id(s)]}
            bands = {b['id'] for p in lay['pages'] if p['page'] in s.pages
                     for b in p['bands'] if b.get('frame', 'page') in frames}
            if any(f.band not in bands for f in s.fields if f.field != 'ignore'):
                raise ValueError(f'{s.name}: unknown amount band in selected reading frame')
    years = {id(s): s.year if s.year is not None else _fallback_year(owned[id(s)]) for s in spec.sections}
    records = []
    order = {v["id"]:i for i,v in enumerate(views)}
    for s in spec.sections:
        cur, ctx = None, {}
        start, roles, ids = compiled[id(s)]
        for v in owned[id(s)]:
            if cur is not None and cur['lines'][-1].get('frame') != v.get('frame'):
                cur = None
            role = next((r for rx, r in roles if _match(rx, v)), None)
            if role in ("header", "noise"):
                continue
            for rx, field, scope in ids:
                if scope == "heading" and rx:
                    code = _code(_search(rx, v))
                    if code:
                        ctx[field] = code
            if _match(start, v):
                cur = {"section": s, "lines": [v], "role": role, "context": dict(ctx)}
                records.append(cur)
            elif cur is not None and len(cur["lines"]) < s.record_lines:
                cur["lines"].append(v)
            else:
                cur = None
    records.sort(key=lambda rec: order[rec["lines"][0]["id"]])
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
        if asset_no:
            asset_no, sub = _unglue(asset_no, first, toks)
            if sub and not ident.get("sub_no"):
                ident["sub_no"] = sub
        year = years[id(s)]
        name = " ".join(toks[c["tid"]]["text"] for c in first["cells"] if c["type"] == "text") or None
        row = {"id": f"r{k}:{first['id']}", "year": year, "unit": s.unit, "kind": kind, "granularity": s.granularity,
               "asset_no": asset_no, "sub_no": ident.get("sub_no"), "class": ident.get("class"),
               "account": ident.get("account"), "position": ident.get("position"), "name": name, "fields": {}}
        primary = {'asset':'asset_no', 'class':'class', 'account':'account', 'position':'position'}[s.granularity]
        missing_identity = kind == 'asset' and not ident.get(primary)
        unidentified = missing_identity or year is None
        problems = []
        if missing_identity:
            problems.append(f'row identity unresolved: {primary}')
        if year is None:
            problems.append('reporting year unresolved')
        if problems:
            row['flags'] = problems
        for fm in s.fields:
            if fm.field == "ignore":
                continue
            field = NET.get(fm.field, fm.field)
            if field in row["fields"]:
                continue
            if unidentified:
                row["fields"][field] = {"amount_column": True, "blank_reason": '; '.join(problems)}
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
                                                "name", "granularity", "unit")} | {"fields": {}, "net_fields": {}, "printed": {},
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


def attach_ocr(doc: dict, path: Path, ocr_dir: Path | None) -> str:
    """Words for pages without a text layer, from a `carth ocr` cache (<stem>.json). The cache must describe the same
    file (same resolved path and page count; same SHA-256 when the cache records one). Text-layer pages keep their exact
    words. Records the provenance in doc["ocr_cache"]; returns a short note for the run log."""
    todo = [p["page"] for p in doc.get("pages", []) if not p["has_text"]]
    if not todo:
        return ""
    cp = ocr_dir / f"{Path(path).stem}.json" if ocr_dir else None
    if not cp or not cp.exists():
        doc["ocr_cache"] = "missing"
        return f"ocr: no cache for {len(todo)} pages"
    from carth import ingest

    c = ingest.load(cp)
    same = (Path(c.get("source", "")).resolve() == Path(path).resolve() and len(c.get("pages", [])) == len(doc["pages"])
            and c.get("sha256") in (None, doc["sha256"]))
    if not same:
        doc["ocr_cache"] = "rejected: different source"
        return "ocr: cache rejected"
    ocr = [dict(t) for t in c["tokens"] if t["page"] in todo]
    for i, t in enumerate(ocr):
        t["id"] = f"o{i}"
    doc["tokens"] = [t for t in doc["tokens"] if t["page"] not in todo] + ocr
    doc["ocr_cache"] = {"engine": (c.get("ocr") or {}).get("engine"), "pages": todo,
                        "verified": "sha256" if c.get("sha256") else "legacy: path + page count only"}
    return f"ocr {doc['ocr_cache']['engine']}: {len(todo)} pages, {len(ocr)} words"


def _one(path: Path, out: Path, model: str | None, doc_id: str, ocr_dir: Path | None = None) -> dict:
    from carth import ingest, output
    from carth.layout import layout
    from carth.spec import DEFAULT_MODEL, infer

    output.check_output_directory(out)
    doc = ingest.ingest(path)
    ocr_note = attach_ocr(doc, path, ocr_dir)
    lay = layout(doc)
    spec, info = infer(lay, model or DEFAULT_MODEL)
    refs = resolve(doc, lay, spec)
    (out / f"{doc_id}.layout.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), "utf-8")
    result = output.extract(doc, refs, doc_id)
    output.write_outputs(result, out)
    (out / "pred").mkdir(parents=True, exist_ok=True)
    (out / "pred" / f"{doc_id}.pred.json").write_text(json.dumps(to_pred(result), ensure_ascii=False), "utf-8")
    vals = [v for v in result["values"] if v["value"] is not None]
    blanks = len(result['values']) - len(vals)
    return {"doc_id": doc_id, "source": str(path.resolve()), "rows": len(result['rows']), "values": len(vals),
            "blanks": blanks, "status": "incomplete" if blanks or result['flags'] else "complete",
            "flags": result['flags'], "seconds": info['seconds'], "cached": bool(info.get('cached')), "ocr": ocr_note}


def main(argv: list[str] | None = None) -> int:
    import argparse
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from carth import ingest, output

    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/m7"))
    ap.add_argument("--types", default="pdf,xlsx")
    ap.add_argument("--docs")
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ocr-tokens", type=Path, default=Path("out/tokens_doctr"),
                    help="`carth ocr` cache for pages without a text layer (default: docTR)")
    a = ap.parse_args(argv)
    output.check_output_directory(a.out)
    if a.workers < 1:
        ap.error('--workers must be positive')
    a.out.mkdir(parents=True, exist_ok=True)
    types = {"." + t for t in a.types.split(",")}
    only = set(a.docs.split(",")) if a.docs else None
    paths = {p:doc_id for p,doc_id in ingest.document_ids(a.input).items()
             if p.suffix.lower() in types and (not only or p.stem in only or doc_id in only)}
    outcomes = []
    with ThreadPoolExecutor(a.workers) as pool:  # the LLM call dominates: threads are enough
        futs = {pool.submit(_one, p, a.out, a.model, doc_id, a.ocr_tokens): p for p,doc_id in paths.items()}
        for f in as_completed(futs):
            try:
                outcome = f.result()
                outcomes.append(outcome)
                print(f"{outcome['doc_id']:<28} {outcome['status']} rows {outcome['rows']} values {outcome['values']} "
                      f"blanks {outcome['blanks']} spec {outcome['seconds']:.1f}s {outcome.get('ocr') or ''}", flush=True)
            except Exception as e:  # one document must not stop the batch
                path = futs[f]
                outcome = {"doc_id": paths[path], "source": str(path.resolve()), "status": "failed",
                           "error": f"{type(e).__name__}: {e}"}
                outcomes.append(outcome)
                print(f"{paths[path]:<28} FAILED {outcome['error'][:160]}", flush=True)
    outcomes.sort(key=lambda o: o['doc_id'])
    failures = [o for o in outcomes if o['status'] == 'failed']
    incomplete = [o for o in outcomes if o['status'] == 'incomplete']
    ingest.save({"failures": failures, "incomplete": incomplete}, a.out / '_failures.json')
    complete = bool(paths) and not failures and not incomplete
    ingest.save({"selected": len(paths), "complete": complete, "documents": outcomes}, a.out / '_batch.json')
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
