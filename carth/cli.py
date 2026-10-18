"""carth command line.

    carth eval   [--corpus DIR] [--pred DIR] [--formats ...] [--ref-tokens DIR] [-v]  strict +1/0/-3 score vs the keys
    carth check  [--corpus DIR] [--pred DIR] [--formats ...]             organisers' check_corpus checks on predictions
    carth ingest [DIR] [--out DIR] [--types pdf,xlsx]                     stage 1: documents -> out/tokens/<stem>.json
    carth ocr    [DIR] [--model small] [--workers N] [--dpi 300] [--docs stem,..]
                 OCR every page without a text layer, in parallel -> out/tokens_<engine>/<stem>.json
    carth recall [--corpus DIR] [--tokens DIR] [--formats ...]           evidence-layer recall against the keys
    carth oracle [--pred DIR] [--mode evidence|key|empty] [--ref-tokens DIR]   key-derived predictions (scorer check)
    carth validate-corpus [FILE_OR_DIR] [--schema PATH]               validate the answer-key JSON contract
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CORPUS = Path("A3-Hackathon-Corpus")
PRED = Path("out/pred")
TOKENS = Path("out/tokens")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="carth")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ev = sub.add_parser("eval", help="score predictions against the answer keys")
    ev.add_argument("--corpus", type=Path, default=CORPUS)
    ev.add_argument("--pred", type=Path, default=PRED)
    ev.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")
    ev.add_argument("-v", "--verbose", action="store_true")
    ev.add_argument("--ref-tokens", type=Path, help="OCR token files used as value references for scans/outlines")

    ck = sub.add_parser("check", help="run the organisers' check_corpus checks on predictions")
    ck.add_argument("--corpus", type=Path, default=CORPUS)
    ck.add_argument("--pred", type=Path, default=PRED)
    ck.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")
    ck.add_argument("--partial", action="store_true", help="allow missing documents for a partial diagnostic")

    ing = sub.add_parser("ingest", help="documents in a folder -> token files (no answer keys)")
    ing.add_argument("input", type=Path, nargs="?", default=CORPUS, help="folder (or file) of documents")
    ing.add_argument("--out", type=Path, default=TOKENS)
    ing.add_argument("--types", help="comma list of file suffixes to keep, e.g. pdf,xlsx")

    oc = sub.add_parser("ocr", help="OCR every page without a text layer, for all documents in a folder")
    oc.add_argument("input", type=Path, nargs="?", default=CORPUS, help="folder (or file) of documents")
    oc.add_argument("--tokens", type=Path, default=TOKENS, help="stage-1 token files to complete, if present")
    oc.add_argument("--out", type=Path, help="default out/tokens_<engine>")
    oc.add_argument("--engine", default="paddle", choices=["paddle", "doctr", "tesseract"])
    oc.add_argument("--model", default="small", help="paddle PP-OCRv6 size: tiny | small | medium")
    oc.add_argument("--dpi", type=int, default=300)
    oc.add_argument("--device", help="paddle device, e.g. cpu (default) or gpu:0")
    oc.add_argument("--workers", type=int, help="parallel OCR processes (default: from RAM and cores)")
    oc.add_argument("--docs", help="comma list of document file stems")
    oc.add_argument("--pages", help="comma list of 1-based pages (debugging)")

    rec = sub.add_parser("recall", help="evidence-layer recall against the keys")
    rec.add_argument("--corpus", type=Path, default=CORPUS)
    rec.add_argument("--tokens", type=Path, default=TOKENS)
    rec.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")
    rec.add_argument("--partial", action="store_true", help="report only available caches")

    orc = sub.add_parser("oracle", help="write predictions derived from the keys")
    orc.add_argument("--corpus", type=Path, default=CORPUS)
    orc.add_argument("--pred", type=Path, default=PRED)
    orc.add_argument("--mode", choices=["key", "empty", "evidence"], default="evidence")
    orc.add_argument("--ref-tokens", type=Path, help="OCR token files used as value references for scans/outlines")

    val = sub.add_parser("validate-corpus", help="validate corpus answer keys against the JSON Schema")
    val.add_argument("input", nargs="?", type=Path, default=CORPUS)
    val.add_argument("--schema", type=Path)

    run = sub.add_parser("run", help="the agent: folder of documents -> per-document JSON + Arbeitsversion.xlsx")
    run.add_argument("input", type=Path)
    run.add_argument("out", type=Path)
    run.add_argument("--specs", type=Path, help="use reviewed <doc_id>.layout.json references instead of the model")
    run.add_argument("--ocr-tokens", type=Path, help="optional `carth ocr` cache; without it OCR runs live (docTR)")
    run.add_argument("--workers", type=int, default=4)

    a = ap.parse_args(argv)
    if a.cmd == "run":
        if a.specs:
            from carth.output import run
            return run(a.input, a.out, a.specs)
        from carth.resolve import main as resolve_main
        args = [str(a.input), "--out", str(a.out), "--workers", str(a.workers)]
        args += ["--ocr-tokens", str(a.ocr_tokens)] if a.ocr_tokens else ["--ocr-tokens", ""]
        return resolve_main(args)
    elif a.cmd == "eval":
        from carth.eval import score
        only = set(a.formats.split(",")) if a.formats else None
        print(score.report(score.score_corpus(a.corpus, a.pred, only, a.ref_tokens), a.verbose))
    elif a.cmd == "check":
        from carth.eval.official import check

        return check(a.corpus, a.pred, set(a.formats.split(",")) if a.formats else None, a.partial)
    elif a.cmd == "ingest":
        from carth import ingest

        types = {"." + t.lower().lstrip(".") for t in a.types.split(",")} if a.types else None
        failures = []
        for path, doc_id in ingest.document_ids(a.input).items():
            if types and path.suffix.lower() not in types:
                continue
            try:
                doc = ingest.ingest(path)
                doc["doc_id"] = doc_id
                ingest.save(doc, a.out / f"{doc_id}.json")
                print(f"{doc_id:<28} {doc['kind']:<9} {len(doc['tokens']):>6} tokens")
            except Exception as exc:
                failures.append({"source": str(path), "doc_id": doc_id, "error": f"{type(exc).__name__}: {exc}"})
        ingest.save({"failures": failures}, a.out / "_failures.json")
        return int(bool(failures))
    elif a.cmd == "ocr":
        import time

        from carth import ingest
        from carth.ingest import ocr

        out = a.out or Path(f"out/tokens_{a.engine}")
        only = set(a.docs.split(",")) if a.docs else None
        pick = {int(x) for x in a.pages.split(",")} if a.pages else None
        docs, jobs, failures = {}, [], []
        for path, doc_id in ingest.document_ids(a.input).items():
            if path.suffix.lower() != ".pdf" or (only and path.stem not in only):
                continue
            tp = a.tokens / f"{doc_id}.json"
            try:
                doc = ingest.load(tp) if tp.exists() else None
                if doc is None or not ingest.cache_matches(doc, path):
                    doc = ingest.ingest(path)
            except Exception as exc:
                failures.append({"source": str(path), "error": f"{type(exc).__name__}: {exc}"})
                continue
            todo = [p["page"] for p in doc.get("pages", []) if p.get("needs_ocr", not p["has_text"]) and (not pick or p["page"] in pick)]
            if todo:
                docs[str(path)] = (doc, todo, doc_id)
                jobs.append((path, todo))
        kw = {"device": a.device, "size": a.model} if a.engine == "paddle" else {}
        workers = a.workers or ocr.auto_workers()
        print(f"OCR {len(jobs)} documents, {sum(len(t) for _, t in jobs)} pages, {workers} workers", flush=True)
        t0 = time.time()
        for path, toks, dt in ocr.ocr_many(jobs, a.engine, kw, a.dpi, workers):
            doc, todo, doc_id = docs[path]
            if isinstance(toks, dict) and "error" in toks:
                failures.append({"source": path, **toks})
                print(f"FAIL {path}: {toks['error']}", flush=True)
                continue
            doc["tokens"] = [t for t in doc["tokens"] if t["page"] not in todo or t.get("src") == "pdf"] + toks
            doc["ocr"] = {"engine": a.engine, "model": ingest.DOCTR_MODEL if a.engine == 'doctr' else a.model,
                          "dpi": a.dpi, "pages": todo,
                          "pipeline_version": ingest.OCR_PIPELINE_VERSION}
            for i, t in enumerate(doc["tokens"]):
                t["id"] = f"t{i}"
            doc["doc_id"] = doc_id
            ingest.save(doc, out / f"{doc_id}.json")
            print(f"{Path(path).stem:<28} {len(todo):>3} pages {len(doc['tokens']):>6} tokens {dt:6.1f}s", flush=True)
        print(f"done in {time.time() - t0:.0f}s", flush=True)
        ingest.save({"failures": failures}, out / "_failures.json")
        return int(bool(failures))
    elif a.cmd == "recall":
        from carth.eval.recall import recall_corpus

        only = set(a.formats.split(",")) if a.formats else None
        print(recall_corpus(a.corpus, a.tokens, only, a.partial))
        if not a.partial:
            from carth.eval.score import load_keys
            return int(any(not (a.tokens / f"{did}.json").exists() for did, (_, k) in load_keys(a.corpus).items()
                           if not only or k["meta"]["format"] in only))
    elif a.cmd == "oracle":
        from carth.eval import score
        a.pred.mkdir(parents=True, exist_ok=True)
        for doc_id, (kp, key) in score.load_keys(a.corpus).items():
            pred = score.oracle_pred(key, a.mode, kp, a.ref_tokens)
            (a.pred / f"{doc_id}.pred.json").write_text(json.dumps(pred), "utf-8")
        print(f"wrote {a.mode} predictions to {a.pred}")
    elif a.cmd == "validate-corpus":
        from carth.eval.validate_corpus import main as validate_main

        options = [str(a.input)]
        if a.schema is not None:
            options += ["--schema", str(a.schema)]
        return validate_main(options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
