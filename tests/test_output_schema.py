"""Extraction contracts: evidence, abstention, metadata, references and scoring."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from carth.cli import main
from carth.output.validate import load_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]


class OutputSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        cls.example = json.loads((ROOT / "docs/examples/example.pred.json").read_text())

    def errors(self, document):
        return validation_errors(document, self.validator)

    def test_multiyear_metadata_without_ground_truth(self):
        self.assertEqual(self.errors(self.example), [])
        self.assertEqual({r["year"] for r in self.example["rows"]}, {2024, 2025})
        for property_name in ("seed", "invented_names", "family", "variant", "trio"):
            with self.subTest(property_name=property_name):
                document = copy.deepcopy(self.example)
                document["meta"][property_name] = 1
                self.assertTrue(self.errors(document))
        document = copy.deepcopy(self.example)
        document["planted"] = []
        self.assertTrue(self.errors(document))

    def test_observation_and_abstention_requirements(self):
        changes = [
            lambda v: v.pop("pointer"),
            lambda v: v.pop("printed"),
            lambda v: v.pop("raw_amount"),
            lambda v: v.update(amount=None),
            lambda v: v.update(amount=True),
            lambda v: v.update(amount=1.5),
            lambda v: v.update(status="derived"),
            lambda v: v.update(printed=""),
            lambda v: v.update(pointer={"sheet":"2025", "cell":"XFE1"}),
            lambda v: v.update(pointer={"sheet":"2025", "cell":"A1048577"}),
            lambda v: v.update(pointer={"page":1, "bbox":[0,0,1,1]}),
        ]
        for mutate in changes:
            document = copy.deepcopy(self.example)
            mutate(document["rows"][0]["fields"]["ahk_close"])
            self.assertTrue(self.errors(document))
        for status in ("unreadable", "absent", "not_applicable", "uncertain"):
            document = copy.deepcopy(self.example)
            value = {"amount":None,"status":status,"reason":"Not available from this source."}
            document["rows"][0]["fields"]["bw_close"] = value
            self.assertEqual(self.errors(document), [])
            value.pop("reason")
            self.assertTrue(self.errors(document))
            value["reason"] = "Not available."
            value["amount"] = 0
            self.assertTrue(self.errors(document))

    def test_empty_output_and_unknown_year_are_explicit(self):
        document = {"schema_version":"1.0","meta":{"doc_id":"unfamiliar","format":"pdf","years":[]},
                    "rows":[],"findings":[{"code":"unreadable_document","severity":"error","message":"No readable schedule."}]}
        self.assertEqual(self.errors(document), [])
        document["findings"] = []
        self.assertTrue(self.errors(document))
        document = copy.deepcopy(self.example)
        document["rows"][0]["year"] = None
        self.assertTrue(self.errors(document))
        document["rows"][0]["year_reason"] = "No period heading on this table."
        self.assertEqual(self.errors(document), [])

    def test_cross_field_invariants(self):
        changes = [
            lambda d: d["rows"][1].update(row_id="r1"),
            lambda d: d["rows"][0].update(year=2023),
            lambda d: d["meta"].update(period_end="2025-02-30"),
            lambda d: d["findings"][0].update(row_id="missing"),
            lambda d: d["findings"][0].update(field="bew_wb"),
            lambda d: d["rows"][0]["fields"].update(ahk_clsoe={"amount":None,"status":"absent","reason":"missing"}),
            lambda d: d["rows"][1].update(fields={}),
        ]
        for mutate in changes:
            document = copy.deepcopy(self.example)
            mutate(document)
            self.assertTrue(self.errors(document))

    def test_pdf_net_movements_and_geometry(self):
        document = {"schema_version":"1.0","meta":{"doc_id":"scan","format":"scan","years":[2025]},
                    "rows":[{"row_id":"r","kind":"asset","level":"class","year":2025,"fields":{
                        "bew_ahk":{"amount":-100000,"status":"observed","printed":"1-","raw_amount":-100000,
                                   "source_unit":"TEUR","pointer":{"page":1,"bbox":[1,2,3,4]}}}}],"findings":[]}
        self.assertEqual(self.errors(document), [])
        for box in ([1,2,1,4], [3,4,1,2], [1,2,float("inf"),4], [-1,2,3,4]):
            document["rows"][0]["fields"]["bew_ahk"]["pointer"]["bbox"] = box
            self.assertTrue(self.errors(document))

    def test_cli_and_ground_truth_are_separate(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["validate-output",str(ROOT/"docs/examples")]),0)
            self.assertEqual(main(["validate-corpus",str(ROOT/"docs/examples/example.pred.json")]),1)
            self.assertEqual(main(["validate-output",str(ROOT/"A3-Hackathon-Corpus/f00_demo/f00_demo_01.key.json")]),1)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"wrong.pred.json"
            path.write_text(json.dumps(self.example))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-output",directory]),1)
            path.write_text('{"amount":NaN}')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-output",directory]),1)

    def test_scorer_observations_abstentions_and_legacy(self):
        from carth.eval.score import score_doc, oracle_pred
        from carth.eval.prediction import for_scoring
        kp=ROOT/"A3-Hackathon-Corpus/f00_demo/f00_demo_01.key.json"
        key=json.loads(kp.read_text())
        r=key["rows"][0]
        value={"amount":r["fields"]["ahk_close"],"status":"observed","printed":r["printed"]["ahk_close"],
               "raw_amount":r["fields"]["ahk_close"],"source_unit":"EUR",
               "pointer":{"sheet":r["pointer"]["sheet"],"cell":r["pointer"]["cells"]["ahk_close"]}}
        document={"schema_version":"1.0","meta":{"doc_id":key["meta"]["doc_id"],"format":"xlsx","years":[r["year"]]},
                  "rows":[{"row_id":"r","kind":"asset","level":"asset","year":r["year"],"fields":{
                      "ahk_close":value,"bw_close":{"amount":None,"status":"uncertain","reason":"Ambiguous text."},
                      "bew_ahk":copy.deepcopy(value)}}],"findings":[]}
        result=score_doc(kp,key,document)
        self.assertEqual((result.right,result.wrong,result.extra),(1,0,0))
        self.assertEqual(result.blank,result.total-1)
        self.assertEqual(document["rows"][0]["fields"]["ahk_close"],value)
        legacy=oracle_pred(key)
        self.assertIs(for_scoring(legacy),legacy)
        self.assertEqual(score_doc(kp,key,legacy).score, result.total)
        document["rows"][0]["fields"]["ahk_close"].pop("pointer")
        with self.assertRaises(ValueError):
            score_doc(kp,key,document)

    def test_checker_handles_new_output_and_reports_bad_source(self):
        from carth.eval.official import check
        with tempfile.TemporaryDirectory() as directory:
            document=copy.deepcopy(self.example)
            doc_id="f00_demo_01"
            document["meta"]["doc_id"]=doc_id
            (Path(directory)/f"{doc_id}.pred.json").write_text(json.dumps(document))
            output=io.StringIO()
            with redirect_stdout(output):
                result=check(ROOT/"A3-Hackathon-Corpus",Path(directory))
            self.assertEqual(result,1)
            self.assertIn("unknown source sheet",output.getvalue())


if __name__ == "__main__":
    unittest.main()
