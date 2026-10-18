"""Evaluation only (M6): does the LLM layout spec map (record line, band) -> field like the answer keys do?

Truth per document, from keys + carth.layout: for every key value found as a token with the printed text (unique in
its row), its (line offset inside the key row, band) votes for its field. The spec is scored per vote:
  right   - the spec maps that (line, band) to the same field
  wrong   - the spec maps it to another field (an "ignore" counts as missing, not wrong)
  missing - the spec has no mapping there
plus whether record_lines matches the most common number of lines per key row.

    python -m carth.eval.spec_metrics --models gpt-6.1-sol,gpt-6-astra [--docs id,…] [--tokens out/tokens]
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from carth import ingest
from carth.eval.frames import centre_in
from carth.eval.score import load_keys
from carth.layout import layout
from carth.spec import infer
from carth.sections import section_views
from carth.resolve import _views

SAMPLE = ["f00_demo_02", "f01_net_spiegel_03", "f02_asset_spiegel_02", "f03_block_spiegel_01", "f04_verzeichnis_01",
          "f05_sap_class_gitter_01", "f06_sap_asset_gitter_07", "f07_sap_class_summary_01", "f08_excel_spiegel_2y_01",
          "f09_excel_register_01"]


def truth(key: dict, lay: dict) -> tuple[dict, dict]:
    """Source-scoped votes (line ID, record offset, band), plus record sizes keyed by first line/bands."""
    votes, sizes = defaultdict(Counter), {}
    toks = lay["tokens"]
    if lay["kind"] == "xlsx":
        line_at = {(sh['sheet'],ln['row']):ln['id'] for sh in lay['sheets'] for ln in sh['lines']}
        at = {(t['sheet'],t['cell']):t for t in toks.values()}
        for row in key['rows']:
            pointer = row['pointer']
            cells = pointer.get('cells', {})
            positions = [int(''.join(c for c in coord if c.isdigit())) for coord in [pointer['cell'],*cells.values()]]
            first = min(positions)
            bands = set()
            for field,coord in cells.items():
                token = at.get((pointer['sheet'],coord))
                if token:
                    line_id = line_at[(pointer['sheet'],token['row'])]
                    votes[(line_id,token['row']-first,token['col'])][field] += 1
                    bands.add(token['col'])
            if (pointer['sheet'],first) in line_at:
                sizes[(line_at[(pointer['sheet'],first)],tuple(sorted(bands)))] = max(positions)-first+1
        return votes,sizes
    line_of, band_of = {}, {}
    by_page = defaultdict(list)
    for page in lay['pages']:
        for ordinal,line in enumerate(page['lines']):
            for cell in line['cells']:
                line_of[cell['tid']] = (ordinal,line['id'])
                band_of[cell['tid']] = cell['band']
    for token in toks.values():
        by_page[token['page']].append(token)
    for row in key['rows']:
        pointer = row['pointer']
        inrow = [t for t in by_page.get(pointer['page'],[]) if centre_in(t['bbox'],pointer['bbox'])]
        if not inrow:
            continue
        first, first_id = min(line_of[t['id']] for t in inrow)
        texts = Counter(t['text'] for t in inrow)
        bands = set()
        for field,printed in row.get('printed',{}).items():
            if printed and texts[printed] == 1:
                token = next(t for t in inrow if t['text']==printed)
                ordinal,line_id = line_of[token['id']]
                band = band_of[token['id']]
                if band is not None:
                    votes[(line_id,ordinal-first,band)][field] += 1
                    bands.add(band)
        sizes[(first_id,tuple(sorted(bands)))] = len({line_of[t['id']] for t in inrow})
    return votes,sizes


def score_spec(spec, votes: dict, lines, lay: dict | None = None) -> dict:
    """Score every vote. Source-scoped votes require the layout to resolve section ownership."""
    owners = defaultdict(list)
    invalid = None
    if lay is not None:
        try:
            views = _views(lay)
            selected = section_views(spec,[v for v in views if v['page'] not in spec.noise_pages])
            for section in spec.sections:
                for view in selected[id(section)]:
                    owners[view['id']].append(section)
        except ValueError as exc:
            invalid = str(exc)
    elif any(len(k)==3 for k in votes):
        raise ValueError('source-scoped votes require a layout')

    right = wrong = missing = 0
    for coordinate,counts in votes.items():
        if len(coordinate)==3:
            line_id,offset,band = coordinate
            sections = owners.get(line_id,[])
        else:  # legacy diagnostics still count every conflicting vote
            offset,band = coordinate
            sections = spec.sections
        matches = {f.field for section in sections for f in section.fields if (f.line,f.band)==(offset,band)}
        got = next(iter(matches)) if len(matches)==1 and not invalid else None
        for field,n in counts.items():
            if got==field:
                right += n
            elif got in (None,'ignore'):
                missing += n
            else:
                wrong += n
    if isinstance(lines,int):
        lines_ok = bool(spec.sections) and all(s.record_lines==lines for s in spec.sections)
    else:
        checks = []
        for (line_id,bands),count in lines.items():
            relevant = [s for s in owners.get(line_id,[]) if any(f.band in bands for f in s.fields)]
            checks.append(bool(relevant) and all(s.record_lines==count for s in relevant))
        lines_ok = bool(checks) and all(checks) and not invalid
    total = right+wrong+missing
    return {'right':right/total if total else 0,'wrong':wrong/total if total else 0,
            'missing':missing/total if total else 0,'lines_ok':bool(lines_ok),
            'sections':len(spec.sections),'n':total,'invalid':invalid}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-6.1-sol")
    ap.add_argument("--docs", default=",".join(SAMPLE))
    ap.add_argument("--tokens", type=Path, default=Path("out/tokens"))
    ap.add_argument("--corpus", type=Path, default=Path("A3-Hackathon-Corpus"))
    a = ap.parse_args()
    keys = load_keys(a.corpus)
    print(f"{'doc':<26}{'model':<14}{'right':>7}{'wrong':>7}{'miss':>7}{'lines':>7}{'secs':>6}{'time':>7}{'in_tok':>8}{'out_tok':>8}")
    agg = defaultdict(lambda: Counter())
    for d in a.docs.split(","):
        lay = layout(ingest.load(a.tokens / f"{d}.json"))
        votes, lines = truth(keys[d][1], lay)
        for model in a.models.split(","):
            try:
                spec, info = infer(lay, model)
            except Exception as e:  # report and go on: one failing call must not hide the others
                print(f"{d:<26}{model:<14} ERROR {type(e).__name__}: {str(e)[:120]}")
                continue
            m = score_spec(spec, votes, lines, lay)
            g = agg[model]
            g["right"] += m["right"] * m["n"]; g["wrong"] += m["wrong"] * m["n"]; g["n"] += m["n"]  # noqa: E702
            g["lines"] += m["lines_ok"]; g["docs"] += 1; g["time"] += info["seconds"]  # noqa: E702
            print(f"{d:<26}{model:<14}{m['right']:>7.2f}{m['wrong']:>7.2f}{m['missing']:>7.2f}"
                  f"{('ok' if m['lines_ok'] else 'mismatch'):>7}{m['sections']:>6}{info['seconds']:>7.1f}"
                  f"{info['input_tokens']:>8}{info['output_tokens']:>8}{' (cached)' if info.get('cached') else ''}",
                  flush=True)
    for model, g in agg.items():
        print(f"TOTAL {model:<20} right {g['right'] / g['n'] if g['n'] else 0:.3f}  wrong {g['wrong'] / g['n'] if g['n'] else 0:.3f}  "
              f"record lines ok {g['lines']}/{g['docs']}  time {g['time']:.0f}s")


if __name__ == "__main__":
    main()
