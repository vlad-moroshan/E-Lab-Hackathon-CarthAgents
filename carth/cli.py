"""carth command line.

    carth eval   [--corpus DIR] [--pred DIR] [--formats xlsx,pdf] [-v]   score predictions against the answer keys
    carth check  [--corpus DIR] [--pred DIR] [--formats ...]             organisers' check_corpus checks on predictions
    carth ingest [--corpus DIR] [--out DIR] [--formats ...]              stage 1: documents -> out/tokens/<doc_id>.json
    carth recall [--corpus DIR] [--tokens DIR] [--formats ...]           evidence-layer recall against the keys
    carth oracle [--corpus DIR] [--pred DIR] [--mode key|empty]          write key-derived predictions (scorer check)
    carth validate-corpus [FILE_OR_DIR] [--schema PATH]               validate the answer-key JSON contract
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from carth.eval import score

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

    ck = sub.add_parser("check", help="run the organisers' check_corpus checks on predictions")
    ck.add_argument("--corpus", type=Path, default=CORPUS)
    ck.add_argument("--pred", type=Path, default=PRED)
    ck.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")

    ing = sub.add_parser("ingest", help="documents -> token files")
    ing.add_argument("--corpus", type=Path, default=CORPUS)
    ing.add_argument("--out", type=Path, default=TOKENS)
    ing.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")

    rec = sub.add_parser("recall", help="evidence-layer recall against the keys")
    rec.add_argument("--corpus", type=Path, default=CORPUS)
    rec.add_argument("--tokens", type=Path, default=TOKENS)
    rec.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")

    orc = sub.add_parser("oracle", help="write predictions derived from the keys")
    orc.add_argument("--corpus", type=Path, default=CORPUS)
    orc.add_argument("--pred", type=Path, default=PRED)
    orc.add_argument("--mode", choices=["key", "empty"], default="key")

    val = sub.add_parser("validate-corpus", help="validate corpus answer keys against the JSON Schema")
    val.add_argument("input", nargs="?", type=Path, default=CORPUS)
    val.add_argument("--schema", type=Path)

    a = ap.parse_args(argv)
    if a.cmd == "eval":
        only = set(a.formats.split(",")) if a.formats else None
        print(score.report(score.score_corpus(a.corpus, a.pred, only), a.verbose))
    elif a.cmd == "check":
        from carth.eval.official import check

        return check(a.corpus, a.pred, set(a.formats.split(",")) if a.formats else None)
    elif a.cmd == "ingest":
        from carth import ingest

        only = set(a.formats.split(",")) if a.formats else None
        for doc_id, (kp, key) in score.load_keys(a.corpus).items():
            if only and key["meta"]["format"] not in only:
                continue
            doc = ingest.ingest(score._doc_path(kp, key))
            ingest.save(doc, a.out / f"{doc_id}.json")
            print(f"{doc_id:<28} {doc['kind']:<9} {len(doc['tokens']):>6} tokens")
    elif a.cmd == "recall":
        from carth.eval.recall import recall_corpus

        print(recall_corpus(a.corpus, a.tokens, set(a.formats.split(",")) if a.formats else None))
    elif a.cmd == "oracle":
        a.pred.mkdir(parents=True, exist_ok=True)
        for doc_id, (_, key) in score.load_keys(a.corpus).items():
            (a.pred / f"{doc_id}.pred.json").write_text(json.dumps(score.oracle_pred(key, a.mode)), "utf-8")
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
