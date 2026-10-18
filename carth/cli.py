"""carth command line.

    carth eval   [--corpus DIR] [--pred DIR] [--formats xlsx,pdf] [-v]   score predictions against the answer keys
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="carth")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ev = sub.add_parser("eval", help="score predictions against the answer keys")
    ev.add_argument("--corpus", type=Path, default=CORPUS)
    ev.add_argument("--pred", type=Path, default=PRED)
    ev.add_argument("--formats", help="comma list of xlsx,pdf,scan,outline")
    ev.add_argument("-v", "--verbose", action="store_true")

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
