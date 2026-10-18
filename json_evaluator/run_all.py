#!/usr/bin/env python3
"""Run every evaluator check on a folder of output JSONs and write one report.

    uv run python json_evaluator/run_all.py PRED_DIR [--corpus DIR] [--out DIR] [--missing-as blank|wrong]
                                          [--baseline OLD/summary.json]

Checks without an answer key (they also run on the hidden test set):
    schema        check_schema.py       format, blanks flagged, printed parses to value
    laws          check_laws.py         row laws, suspect field
    totals        check_totals.py       subtotals tie, transfers net to 0, year-to-year carry forward
    pointers      check_pointers.py     value really sits at its pointer in the source document
    completeness  check_completeness.py every schedule line of the source is in the output
Checks against the answer key (sample set only):
    score         score.py              +1 / 0 / -3, wrong-value causes and size, flags, secondary fields
    planted       check_planted.py      each planted problem handled as its expected_behaviour asks

Writes OUT/summary.json, OUT/summary.md and OUT/docs/<doc_id>.json (default OUT = PRED_DIR/_eval).
Exit 1 when a document fails the schema, or the total score falls below --baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_laws  # noqa: E402
import check_planted  # noqa: E402
import check_schema  # noqa: E402
import check_totals  # noqa: E402
import score  # noqa: E402
from common import DEFAULT_CORPUS, Corpus, iter_predictions, load  # noqa: E402

import check_completeness  # noqa: E402
import check_pointers  # noqa: E402

try:  # the source checks read the documents with pdfplumber / openpyxl (project dependencies)
    import openpyxl  # noqa: F401
    import pdfplumber  # noqa: F401
    HAVE_SOURCE_CHECKS = True
except ImportError:
    HAVE_SOURCE_CHECKS = False


def _sev(issues):
    c = Counter(i["severity"] for i in issues)
    return {"error": c["error"], "warn": c["warn"], "info": c["info"]}


def evaluate_doc(doc_id: str, path: Path, corpus: Corpus, missing_as: str) -> dict:
    pred = load(path)
    rep = {"doc_id": doc_id, "file": str(path), "checks": {}}
    schema = check_schema.check(pred)
    rep["checks"]["schema"] = {"summary": _sev(schema), "issues": schema}
    if any(i["severity"] == "error" and i["message"] in ("missing meta", "no rows") for i in schema):
        return rep
    for name, mod in (("laws", check_laws), ("totals", check_totals)):
        iss = mod.check(pred)
        rep["checks"][name] = {"summary": _sev(iss), "issues": iss}
    source = corpus.source(doc_id)
    if HAVE_SOURCE_CHECKS:
        for name, mod in (("pointers", check_pointers), ("completeness", check_completeness)):
            try:
                iss, st = mod.check(pred, source)
            except Exception as e:  # a broken source must not stop the run
                iss, st = [{"check": name, "severity": "error", "message": f"{type(e).__name__}: {e}"}], {}
            rep["checks"][name] = {"summary": _sev(iss), "stats": st, "issues": iss}
    key = corpus.key(doc_id)
    if key is not None:
        rep["score"] = score.score_doc(pred, key, missing_as)
        rep["planted"] = check_planted.evaluate(pred, key)
    return rep


def summarize(reports: list[dict]) -> dict:
    tot = Counter()
    groups = {g: defaultdict(Counter) for g in ("family", "format", "variant")}
    by_field, by_kind, causes, mags, flags = defaultdict(Counter), defaultdict(Counter), Counter(), Counter(), \
        defaultdict(Counter)
    checks = defaultdict(Counter)
    planted = defaultdict(Counter)
    pointer_stats, compl_stats = Counter(), Counter()
    for r in reports:
        for name, c in r["checks"].items():
            checks[name].update(c["summary"])
            checks[name]["docs_with_errors"] += bool(c["summary"]["error"])
        pointer_stats.update({k: v for k, v in r["checks"].get("pointers", {}).get("stats", {}).items()
                              if isinstance(v, int)})
        compl_stats.update({k: v for k, v in r["checks"].get("completeness", {}).get("stats", {}).items()
                            if isinstance(v, int) and not isinstance(v, bool)})
        s = r.get("score")
        if not s:
            continue
        tot.update(s["counts"])
        tot["score"] += s["score"]
        tot["values"] += s["values"]
        tot["docs"] += 1
        for g in groups:
            groups[g][s[g]].update(s["counts"])
            groups[g][s[g]]["score"] += s["score"]
            groups[g][s[g]]["values"] += s["values"]
        for f, c in s["by_field"].items():
            by_field[f].update(c)
        for k, c in s["by_kind"].items():
            by_kind[k].update(c)
        causes.update(s["wrong_causes"])
        mags.update(s["wrong_magnitude"])
        for reason, c in s["flags"].items():
            flags[reason].update(c)
        for p in r.get("planted", []):
            planted[p["type"]]["pass" if p["pass"] else "fail"] += 1

    def pct(c):
        return round(100 * c["score"] / c["values"], 2) if c.get("values") else None

    return {
        "documents": len(reports), "scored_documents": tot["docs"],
        "total": {"score": tot["score"], "values": tot["values"], "score_pct": pct(tot),
                  **{o: tot[o] for o in ("correct", "blank", "wrong", "missing")}},
        **{f"by_{g}": {k: {**dict(c), "score_pct": pct(c)} for k, c in sorted(v.items())} for g, v in groups.items()},
        "by_field": {f: dict(c) for f, c in sorted(by_field.items())},
        "by_kind": {k: dict(c) for k, c in sorted(by_kind.items())},
        "wrong_causes": dict(causes.most_common()), "wrong_magnitude": dict(mags),
        "flags": {r: dict(c) for r, c in flags.items()}, "planted": {t: dict(c) for t, c in sorted(planted.items())},
        "checks": {n: dict(c) for n, c in checks.items()},
        "pointer_reread": dict(pointer_stats), "completeness": dict(compl_stats),
    }


def to_markdown(summary: dict, reports: list[dict]) -> str:
    t = summary["total"]
    L = ["# Evaluation report", ""]
    if t["values"]:
        L += [f"**Score {t['score']} / {t['values']} ({t['score_pct']}%)**: correct {t['correct']}, "
              f"blank {t['blank']}, wrong {t['wrong']}, missing {t['missing']} "
              f"({summary['scored_documents']} documents with an answer key)", ""]
    L += ["## Checks (no answer key needed)", "", "| check | errors | warnings | docs with errors |", "|---|---|---|---|"]
    for n, c in summary["checks"].items():
        L.append(f"| {n} | {c.get('error', 0)} | {c.get('warn', 0)} | {c.get('docs_with_errors', 0)} |")
    pr, co = summary["pointer_reread"], summary["completeness"]
    if pr:
        L += ["", f"Pointer re-read: {pr.get('verified', 0)} verified, {pr.get('failed', 0)} failed, "
                  f"{pr.get('unverifiable', 0)} not verifiable (no text layer)"]
    if co:
        L += [f"Completeness: {co.get('data_lines', 0)} schedule lines in the sources, {co.get('covered', 0)} covered, "
              f"{co.get('uncovered', 0)} not in the output, {co.get('short_rows', 0)} rows with amounts left out"]
    for g in ("family", "format", "variant"):
        rows = summary[f"by_{g}"]
        if not rows:
            continue
        L += ["", f"## By {g}", "", f"| {g} | score % | correct | blank | wrong | missing |", "|---|---|---|---|---|---|"]
        for k, c in rows.items():
            L.append(f"| {k} | {c['score_pct']} | {c.get('correct', 0)} | {c.get('blank', 0)} | {c.get('wrong', 0)} "
                     f"| {c.get('missing', 0)} |")
    if summary["by_field"]:
        L += ["", "## By field", "", "| field | correct | blank | wrong | missing |", "|---|---|---|---|---|"]
        for f, c in summary["by_field"].items():
            L.append(f"| {f} | {c.get('correct', 0)} | {c.get('blank', 0)} | {c.get('wrong', 0)} | {c.get('missing', 0)} |")
    if summary["wrong_causes"]:
        L += ["", "## Wrong values", "", "Causes: " + ", ".join(f"{k} {v}" for k, v in summary["wrong_causes"].items()),
              "", "How far off: " + ", ".join(f"{k} {v}" for k, v in summary["wrong_magnitude"].items())]
    if summary["flags"]:
        L += ["", "## Flags vs key", "", "| key flag | caught | missed | extra |", "|---|---|---|---|"]
        for r, c in summary["flags"].items():
            L.append(f"| {r} | {c.get('caught', 0)} | {c.get('missed', 0)} | {c.get('extra', 0)} |")
    if summary["planted"]:
        L += ["", "## Planted problems", "", "| type | pass | fail |", "|---|---|---|"]
        for tname, c in summary["planted"].items():
            L.append(f"| {tname} | {c.get('pass', 0)} | {c.get('fail', 0)} |")
    L += ["", "## Documents", "", "| doc | score % | wrong | blank | missing | schema err | law err | total err "
                                  "| pointer err | uncovered lines |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        s, ch = r.get("score") or {}, r["checks"]
        c = s.get("counts", {})
        L.append(f"| {r['doc_id']} | {s.get('score_pct', '')} | {c.get('wrong', 0)} | {c.get('blank', 0)} | "
                 f"{c.get('missing', 0)} | {ch['schema']['summary']['error']} | "
                 f"{ch.get('laws', {}).get('summary', {}).get('error', '')} | "
                 f"{ch.get('totals', {}).get('summary', {}).get('error', '')} | "
                 f"{ch.get('pointers', {}).get('summary', {}).get('error', '')} | "
                 f"{ch.get('completeness', {}).get('stats', {}).get('uncovered', '')} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run every evaluator check on a folder of output JSONs.")
    ap.add_argument("pred_dir")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--out")
    ap.add_argument("--missing-as", choices=("blank", "wrong"), default="blank")
    ap.add_argument("--baseline", help="summary.json of an earlier run; exit 1 if the score drops")
    a = ap.parse_args(argv)
    pred_dir = Path(a.pred_dir)
    out = Path(a.out) if a.out else pred_dir / "_eval"
    (out / "docs").mkdir(parents=True, exist_ok=True)
    corpus = Corpus(Path(a.corpus))
    if not HAVE_SOURCE_CHECKS:
        print("note: pdfplumber/openpyxl missing; pointer and completeness checks skipped (use uv run)")

    reports = []
    for doc_id, path in iter_predictions(pred_dir):
        rep = evaluate_doc(doc_id, path, corpus, a.missing_as)
        reports.append(rep)
        (out / "docs" / f"{doc_id}.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
        s = rep.get("score")
        errs = {n: c["summary"]["error"] for n, c in rep["checks"].items() if c["summary"]["error"]}
        print(f"{doc_id:28s} " + (f"score {s['score_pct']:6.2f}%  wrong {s['counts'].get('wrong', 0):4d}  "
                                  if s else "no key            ") + (f"errors {errs}" if errs else "checks clean"))

    summary = summarize(reports)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(to_markdown(summary, reports), encoding="utf-8")
    t = summary["total"]
    if t["values"]:
        print(f"\nTOTAL score {t['score']} / {t['values']} ({t['score_pct']}%)  correct {t['correct']}  "
              f"blank {t['blank']}  wrong {t['wrong']}  missing {t['missing']}")
    print(f"report: {out / 'summary.md'}")

    rc = 1 if summary["checks"].get("schema", {}).get("docs_with_errors") else 0
    if a.baseline:
        old = json.loads(Path(a.baseline).read_text(encoding="utf-8"))["total"]["score"]
        if t["score"] < old:
            print(f"REGRESSION: score {t['score']} < baseline {old}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
