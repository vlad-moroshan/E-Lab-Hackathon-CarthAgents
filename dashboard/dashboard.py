#!/usr/bin/env python3
"""Build a browser dashboard for one evaluation run (one method's output folder).

The run is a folder written by run_all.py (summary.json + docs/), or the output folder that holds it in _eval/.
To compare methods, build one dashboard per method folder.

    uv run python dashboard/dashboard.py out/tesseract [--label tesseract] [-o FILE] [--open]

Writes <eval folder>/dashboard.html by default: one self-contained HTML file (no network) with
    Overview    score, outcomes, score by format, family and variant, causes and size of wrong values,
                outcome per field, flags vs the key, checks without a key, planted problems
    Documents   every document of the run, filterable; click one for its wrong values and check findings
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_WRONG = 40     # wrong values kept per document and method
MAX_ISSUES = 15    # check issues kept per document, check and method


def eval_dir(path: Path) -> Path:
    for d in (path, path / "_eval"):
        if (d / "summary.json").is_file():
            return d
    raise SystemExit(f"{path}: no summary.json (run json_evaluator/run_all.py on it first)")


def slim_doc(rep: dict) -> dict:
    s = rep.get("score") or {}
    checks = {}
    for name, c in rep.get("checks", {}).items():
        checks[name] = {
            "error": c["summary"]["error"], "warn": c["summary"]["warn"],
            "issues": [{k: i.get(k) for k in ("severity", "row", "where", "field", "message")}
                       for i in c.get("issues", []) if i.get("severity") in ("error", "warn")][:MAX_ISSUES],
        }
    st = rep.get("checks", {}).get("pointers", {}).get("stats", {})
    co = rep.get("checks", {}).get("completeness", {}).get("stats", {})
    return {
        "id": rep["doc_id"], "family": s.get("family"), "format": s.get("format"), "variant": s.get("variant"),
        "score": s.get("score"), "values": s.get("values"), "score_pct": s.get("score_pct"),
        "counts": s.get("counts", {}), "precision": s.get("precision"),
        "causes": s.get("wrong_causes", {}), "wrong": (s.get("wrong_values") or [])[:MAX_WRONG],
        "planted": rep.get("planted", []), "checks": checks,
        "pointer": {k: st.get(k, 0) for k in ("verified", "failed", "unverifiable")},
        "uncovered": co.get("uncovered") if co.get("checkable", True) else None,
        "meta_diff": s.get("meta_diff", {}),
    }


def load_run(label: str, path: Path) -> dict:
    d = eval_dir(path)
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    docs = [slim_doc(json.loads(p.read_text(encoding="utf-8"))) for p in sorted((d / "docs").glob("*.json"))]
    return {"label": label, "path": str(d), "summary": summary, "docs": docs,
            "built": dt.datetime.fromtimestamp((d / "summary.json").stat().st_mtime).strftime("%Y-%m-%d %H:%M")}


def build(run: dict) -> str:
    data = json.dumps({"run": run, "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M")},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (HERE / "dashboard_template.html").read_text(encoding="utf-8").replace("__DATA__", data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Browser dashboard for one evaluation run.")
    ap.add_argument("run", help="folder with summary.json, or the output folder that holds it in _eval/")
    ap.add_argument("--label", help="name shown in the dashboard (default: the output folder's name)")
    ap.add_argument("-o", "--out", help="output HTML (default: <eval folder>/dashboard.html)")
    ap.add_argument("--open", action="store_true", help="open the dashboard in the default browser")
    a = ap.parse_args(argv)
    p = Path(a.run).expanduser()
    d = eval_dir(p)
    label = a.label or (d.parent.name if d.name == "_eval" else d.name)
    run = load_run(label, p)
    out = Path(a.out) if a.out else d / "dashboard.html"
    out.write_text(build(run), encoding="utf-8")
    print(f"dashboard: {out.resolve()}  ({label}, {len(run['docs'])} documents)")
    if a.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
