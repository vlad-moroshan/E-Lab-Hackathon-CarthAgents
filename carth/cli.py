"""carth command line.

    carth eval   [--corpus DIR] [--pred DIR] [--formats xlsx,pdf] [-v]   score predictions against the answer keys
    carth oracle [--corpus DIR] [--pred DIR] [--mode key|empty]          write key-derived predictions (scorer check)
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

    a = ap.parse_args(argv)
    if a.cmd == "eval":
        only = set(a.formats.split(",")) if a.formats else None
        print(score.report(score.score_corpus(a.corpus, a.pred, only), a.verbose))
    elif a.cmd == "oracle":
        a.pred.mkdir(parents=True, exist_ok=True)
        for doc_id, (_, key) in score.load_keys(a.corpus).items():
            (a.pred / f"{doc_id}.pred.json").write_text(json.dumps(score.oracle_pred(key, a.mode)), "utf-8")
        print(f"wrote {a.mode} predictions to {a.pred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
