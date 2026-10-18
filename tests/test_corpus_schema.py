"""Whole-corpus acceptance and rejection of malformed answer-key records."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from carth.eval.validate_corpus import load_validator, validation_errors


class CorpusSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        cls.corpus = Path(__file__).resolve().parents[1] / "A3-Hackathon-Corpus"
        cls.fixture = json.loads((cls.corpus / "f00_demo/f00_demo_01.key.json").read_text())

    def test_all_supplied_keys(self):
        paths = sorted(self.corpus.rglob("*.key.json"))
        self.assertTrue(paths, "Corpus must not be empty")
        families = set()
        for path in paths:
            with self.subTest(path=path.relative_to(self.corpus)):
                document = json.loads(path.read_text())
                self.assertEqual(validation_errors(document, self.validator), [])
                self.assertEqual(document["meta"]["doc_id"], path.name.removesuffix(".key.json"))
                families.add(document["meta"]["family"])
        self.assertEqual(len(families), 10)

    def test_malformed_records_are_rejected(self):
        cases = [
            ("missing envelope member", lambda d: d.pop("planted")),
            ("unknown property", lambda d: d.update({"unexpected": True})),
            ("unknown field", lambda d: d["rows"][0]["fields"].update({"ahk_clsoe": 100})),
            ("amount as string", lambda d: d["rows"][0]["fields"].update({"ahk_open": "123,45"})),
            ("fractional cents", lambda d: d["rows"][0]["fields"].update({"ahk_open": 1.25})),
            ("null amount", lambda d: d["rows"][0]["fields"].update({"ahk_open": None})),
            ("boolean amount", lambda d: d["rows"][0]["fields"].update({"ahk_open": True})),
            ("negative magnitude", lambda d: d["rows"][0]["fields"].update({"ahk_open": -100})),
            ("invalid unit", lambda d: d["meta"].update({"unit": "USD"})),
            ("impossible date", lambda d: d["meta"].update({"period_end": "2025-02-30"})),
            ("wrong pointer for format", lambda d: d["meta"].update({"format": "pdf"})),
            ("bad cell address", lambda d: d["rows"][0]["pointer"].update({"cell": "A0"})),
            ("missing printed field", lambda d: d["rows"][0]["printed"].pop("ahk_open")),
            ("year outside document", lambda d: d["rows"][0].update({"year": 1999})),
            ("wrong document family", lambda d: d["meta"].update({"family": "other"})),
            ("unknown flag", lambda d: d["rows"][0].update({"flags": {"*": "guessed"}})),
            ("missing problem location", lambda d: d["planted"].append({
                "type": "glued_numbers", "where": [{}], "expected_behaviour": "split amounts"
            })),
        ]
        for name, mutate in cases:
            with self.subTest(case=name):
                document = copy.deepcopy(self.fixture)
                mutate(document)
                self.assertTrue(validation_errors(document, self.validator))

    def test_pdf_pointer_shape_and_geometry(self):
        path = self.corpus / "f00_demo/f00_demo_02.key.json"
        original = json.loads(path.read_text())
        for change in ({"page": 0}, {"bbox": [1, 2, 3]}, {"bbox": [10, 20, 1, 2]}):
            with self.subTest(change=change):
                document = copy.deepcopy(original)
                document["rows"][0]["pointer"].update(change)
                self.assertTrue(validation_errors(document, self.validator))

    def test_signed_transfers_and_net_movements_are_allowed(self):
        document = copy.deepcopy(self.fixture)
        document["rows"][0]["fields"]["umbuchung"] = -12345
        self.assertEqual(validation_errors(document, self.validator), [])
        path = self.corpus / "f07_sap_class_summary/f07_sap_class_summary_01.key.json"
        document = json.loads(path.read_text())
        document["rows"][0]["net_fields"]["bew_ahk"] = -12345
        self.assertEqual(validation_errors(document, self.validator), [])

    def test_cli_validates_files_and_returns_failure_for_invalid_json(self):
        from carth.cli import main

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["validate-corpus", str(self.corpus / "f00_demo/f00_demo_01.key.json")])
        self.assertEqual(result, 0)
        self.assertIn("1 documents: 1 valid, 0 invalid", output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{"meta": {}}')
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["validate-corpus", str(path)])
            self.assertEqual(result, 1)
            self.assertIn("1 documents: 0 valid, 1 invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
