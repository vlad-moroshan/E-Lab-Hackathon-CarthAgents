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

SAMPLE = ["f00_demo_02", "f01_net_spiegel_03", "f02_asset_spiegel_02", "f03_block_spiegel_01", "f04_verzeichnis_01",
          "f05_sap_class_gitter_01", "f06_sap_asset_gitter_07", "f07_sap_class_summary_01", "f08_excel_spiegel_2y_01",
          "f09_excel_register_01"]


def truth(key: dict, lay: dict) -> tuple[dict, int]:
    """({(line offset, band): Counter(field)}, most common lines per row)."""
    votes, nlines = defaultdict(Counter), Counter()
    toks = lay["tokens"]
    if lay["kind"] == "xlsx":
        band = {c["tid"]: c["band"] for sh in lay["sheets"] for ln in sh["lines"] for c in ln["cells"]}
        at = {(t["sheet"], t["cell"]): t for t in toks.values()}
        for r in key["rows"]:
            p = r["pointer"]
            cells = p.get("cells", {})
            rows = [int("".join(ch for ch in c if ch.isdigit())) for c in [p["cell"], *cells.values()]]
            nlines[max(rows) - min(rows) + 1] += 1
            for f, coord in cells.items():
                t = at.get((p["sheet"], coord))
                if t and band.get(t["id"]) is not None:
                    votes[(int("".join(ch for ch in coord if ch.isdigit())) - min(rows), band[t["id"]])][f] += 1
        return votes, nlines.most_common(1)[0][0] if nlines else 1
    line_idx, band = {}, {}
    for pg in lay["pages"]:
        for k, ln in enumerate(pg["lines"]):
            for c in ln["cells"]:
                line_idx[c["tid"]], band[c["tid"]] = (pg["page"], k), c["band"]
    by_page = defaultdict(list)
    for t in toks.values():
        by_page[t["page"]].append(t)
    for r in key["rows"]:
        p = r["pointer"]
        inrow = [t for t in by_page.get(p["page"], []) if centre_in(t["bbox"], p["bbox"])]
        if not inrow:
            continue
        first = min(line_idx[t["id"]][1] for t in inrow)
        nlines[len({line_idx[t["id"]] for t in inrow})] += 1
        texts = Counter(t["text"] for t in inrow)
        for f, printed in r.get("printed", {}).items():
            if printed and texts[printed] == 1:
                t = next(t for t in inrow if t["text"] == printed)
                if band[t["id"]] is not None:
                    votes[(line_idx[t["id"]][1] - first, band[t["id"]])][f] += 1
    return votes, nlines.most_common(1)[0][0] if nlines else 1


def score_spec(spec, votes: dict, lines: int) -> dict:
    mapped = {}
    for s in spec.sections:
        for m in s.fields:
            mapped.setdefault((m.line, m.band), m.field)
    right = wrong = missing = 0
    for k, c in votes.items():
        f, n = c.most_common(1)[0]
        got = mapped.get(k)
        if got == f:
            right += n
        elif got in (None, "ignore"):
            missing += n
        else:
            wrong += n
    total = right + wrong + missing
    return {"right": right / total if total else 0, "wrong": wrong / total if total else 0,
            "missing": missing / total if total else 0, "lines_ok": any(s.record_lines == lines for s in spec.sections),
            "sections": len(spec.sections), "n": total}


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
            m = score_spec(spec, votes, lines)
            g = agg[model]
            g["right"] += m["right"] * m["n"]; g["wrong"] += m["wrong"] * m["n"]; g["n"] += m["n"]  # noqa: E702
            g["lines"] += m["lines_ok"]; g["docs"] += 1; g["time"] += info["seconds"]  # noqa: E702
            print(f"{d:<26}{model:<14}{m['right']:>7.2f}{m['wrong']:>7.2f}{m['missing']:>7.2f}"
                  f"{('ok' if m['lines_ok'] else f'≠{lines}'):>7}{m['sections']:>6}{info['seconds']:>7.1f}"
                  f"{info['input_tokens']:>8}{info['output_tokens']:>8}{' (cached)' if info.get('cached') else ''}",
                  flush=True)
    for model, g in agg.items():
        print(f"TOTAL {model:<20} right {g['right'] / g['n']:.3f}  wrong {g['wrong'] / g['n']:.3f}  "
              f"record lines ok {g['lines']}/{g['docs']}  time {g['time']:.0f}s")


if __name__ == "__main__":
    main()
