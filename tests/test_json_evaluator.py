"""The JSON evaluator must score the answer keys perfectly and catch every planted mistake in its self-test."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "json_evaluator"
sys.path.insert(0, str(EVAL))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EVAL / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class JsonEvaluatorTest(unittest.TestCase):
    def test_selftest_catches_every_planted_mistake(self):
        self.assertEqual(_load("selftest").main(), 0)

    def test_pred_json_naming_and_per_value_pointers(self):
        common, run_all = _load("common"), _load("run_all")
        corpus = common.Corpus()
        key = corpus.key("f00_demo_01")
        for row in key["rows"]:  # move the per-field cells into carth's per-value `pointers`
            row["pointers"] = {f: {"sheet": row["pointer"]["sheet"], "cell": c}
                               for f, c in row["pointer"].pop("cells").items()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f00_demo_01.pred.json"
            path.write_text(json.dumps(key), encoding="utf-8")
            [(doc_id, _)] = list(common.iter_predictions(Path(tmp)))
            self.assertEqual(doc_id, "f00_demo_01")
            rep = run_all.evaluate_doc(doc_id, path, corpus, "blank")
        self.assertEqual(rep["score"]["score"], rep["score"]["values"])
        self.assertEqual(rep["checks"]["pointers"]["stats"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
