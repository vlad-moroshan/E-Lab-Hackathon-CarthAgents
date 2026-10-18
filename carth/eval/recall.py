"""Evidence-layer recall: can every amount the key expects be found in our tokens, at the key's location?

PDF (per key value with a non-empty printed string), tokens whose centre lies in the key row's bbox:
  exact   - one token's text == printed                  (extraction can take it as is)
  inside  - printed is a substring of one token          (glued amounts, id glued to text: needs splitting)
  joined  - printed is in the row text, spaces removed  (split over several tokens)
  missing - not found                                    (OCR error, cut off, or a bug in ingest)
xlsx (per key value with a cell): the token at that cell holds the value (the check_corpus.xlsx_checks rule).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from carth import ingest
from carth.eval.score import load_keys


def _centre_in(t, bbox, pad=0.5) -> bool:
    cx, cy = (t["bbox"][0] + t["bbox"][2]) / 2, (t["bbox"][1] + t["bbox"][3]) / 2
    return bbox[0] - pad <= cx <= bbox[2] + pad and bbox[1] - pad <= cy <= bbox[3] + pad


def doc_recall(key: dict, doc: dict) -> Counter:
    c = Counter()
    if doc["kind"] == "xlsx":
        scale = 100_000 if key["meta"]["unit"] == "TEUR" else 100
        at = {(t["sheet"], t["cell"]): t for t in doc["tokens"]}
        for r in key["rows"]:
            p = r["pointer"]
            for f, coord in p.get("cells", {}).items():
                t, want, printed = at.get((p["sheet"], coord)), r["fields"][f], r["printed"][f]
                v = t["value"] if t else None
                ok = ((v is None and want == 0 and not printed)
                      or (isinstance(v, (int, float)) and abs(round(v * scale)) == abs(want))
                      or (isinstance(v, str) and v == printed))
                c["exact" if ok else "missing"] += 1
                c["hidden"] += bool(t and t["hidden"])
        return c
    by_page = defaultdict(list)
    for t in doc["tokens"]:
        by_page[t["page"]].append(t)
    for r in key["rows"]:
        p = r["pointer"]
        toks = [t for t in by_page.get(p["page"], []) if _centre_in(t, p["bbox"])]
        texts = [t["text"] for t in toks]
        joined = "".join(texts)
        for f, printed in r.get("printed", {}).items():
            if not printed:
                continue
            if printed in texts:
                c["exact"] += 1
            elif any(printed in s for s in texts):
                c["inside"] += 1
            elif printed in joined:
                c["joined"] += 1
            else:
                c["missing"] += 1
    return c


def recall_corpus(corpus: Path, tokens_dir: Path, only: set[str] | None = None) -> str:
    rows, tot = [], Counter()
    by_fmt = defaultdict(Counter)
    for doc_id, (_, key) in load_keys(corpus).items():
        fmt = key["meta"]["format"]
        tp = tokens_dir / f"{doc_id}.json"
        if (only and fmt not in only) or not tp.exists():
            continue
        c = doc_recall(key, ingest.load(tp))
        rows.append((doc_id, fmt, c))
        tot += c
        by_fmt[fmt] += c

    def line(name, c):
        n = c["exact"] + c["inside"] + c["joined"] + c["missing"]
        pct = lambda k: 100 * c[k] / n if n else 0  # noqa: E731
        return (f"{name:<28}{n:>7}{pct('exact'):>8.1f}{pct('inside'):>8.1f}{pct('joined'):>8.1f}"
                f"{pct('missing'):>8.1f}{c['hidden']:>8}")

    head = f"{'doc':<28}{'values':>7}{'exact%':>8}{'inside%':>8}{'joined%':>8}{'miss%':>8}{'hidden':>8}"
    out = [head, "-" * len(head)]
    out += [line(d, c) for d, _, c in rows if c["missing"] or c["inside"] or c["joined"]]
    out += ["", *[line(f"format={f}", c) for f, c in sorted(by_fmt.items())], line("TOTAL", tot)]
    return "\n".join(out)
