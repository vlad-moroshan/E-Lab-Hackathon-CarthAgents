"""Experiment isolation, source-only algorithms and repeatable local evaluation."""

from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carth.pipeline.algorithms import TableSpec, abstain, mapped_xlsx
from carth.pipeline.amounts import parse_cents
from carth.pipeline.experiment import evaluate_run, load_evidence, run_experiment, select_inputs
from carth.output.check import check_document

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "A3-Hackathon-Corpus/f00_demo"


class ExperimentTests(unittest.TestCase):
    def test_parser_does_not_guess(self):
        self.assertEqual(parse_cents("1.234,56-"), -123456)
        self.assertEqual(parse_cents("(1,234.56)", decimal="."), -123456)
        self.assertEqual(parse_cents("1.235", unit="TEUR"), 123500000)
        self.assertEqual(parse_cents(1.25), 125)
        for value in (None, True, "", "12??", "1.234,564.321,00", "1,001", float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_cents(value)

    def test_selection_ignores_keys_and_locks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one.xlsx", "~$one.xlsx", "one.key.json", "two.pdf"):
                (root/name).touch()
            self.assertEqual([s.doc_id for s in select_inputs(root)], ["one", "two"])
            with self.assertRaises(ValueError):
                select_inputs(root, suffixes=(".docx",))
            (root/"one.pdf").touch()
            with self.assertRaisesRegex(ValueError, "duplicate"):
                select_inputs(root)

    def test_mapped_algorithm_and_evaluation(self):
        samples = select_inputs(DEMO, suffixes=(".xlsx",))
        original_read = Path.read_text

        def no_keys(path, *args, **kwargs):
            if str(path).endswith(".key.json"):
                raise AssertionError("Extraction read an answer key")
            return original_read(path, *args, **kwargs)

        with TemporaryDirectory() as directory, patch.object(Path, "read_text", no_keys):
            evidence = load_evidence(samples)
            table = TableSpec(sheet=evidence[samples[0].doc_id]["sheets"][0]["sheet"], year=2025,unit="EUR",first_row=8,
                              columns={"ahk_close":"G","bw_close":"M"},identity_column="A",name_column="B")
            run = run_experiment(samples, {"blank":abstain,"mapped":partial(mapped_xlsx,spec=table)},
                                 evidence=evidence, output_root=Path(directory))
            self.assertTrue(run.outputs["mapped"][samples[0].doc_id]["rows"])
            self.assertTrue(all(not m["check_errors"] for m in run.metrics))
            with self.assertRaises(AssertionError):
                evaluate_run(run)
            with patch.object(Path, "read_text", original_read):
                evaluation = evaluate_run(run)
                baseline, mapped = evaluation["summary"]
                self.assertEqual(baseline["score"],0)
                self.assertGreater(mapped["right"],0)
                self.assertEqual(mapped["wrong"],0)
                self.assertEqual(mapped["extra"],0)
                self.assertEqual(evaluation["missing_keys"],[])
                self.assertTrue((run.directory/"evaluation.json").exists())
            rerun = run_experiment(samples,{"blank":abstain},evidence=evidence,output_root=Path(directory))
            self.assertNotEqual(run.directory,rerun.directory)

    def test_algorithm_evidence_isolation_and_invalid_output(self):
        samples = select_inputs(DEMO,suffixes=(".xlsx",))
        evidence = load_evidence(samples)
        original_count = len(evidence[samples[0].doc_id]["tokens"])

        def mutate(doc, doc_id):
            doc["tokens"].clear()
            return abstain(doc, doc_id)

        def assert_intact(doc, doc_id):
            self.assertEqual(len(doc["tokens"]),original_count)
            return abstain(doc, doc_id)

        with TemporaryDirectory() as directory:
            run_experiment(samples,{"mutate":mutate,"intact":assert_intact},evidence=evidence,output_root=Path(directory))
            self.assertEqual(len(evidence[samples[0].doc_id]["tokens"]),original_count)
            with self.assertRaisesRegex(ValueError,"invalid"):
                run_experiment(samples,{"invalid":lambda doc,doc_id:{}},evidence=evidence,output_root=Path(directory))

    def test_native_checker_and_cli_accept_output(self):
        from carth.eval.official import check
        from contextlib import redirect_stdout
        import io

        samples=select_inputs(DEMO,suffixes=(".xlsx",))
        evidence=load_evidence(samples)
        table=TableSpec(sheet=evidence[samples[0].doc_id]["sheets"][0]["sheet"],year=2025,unit="EUR",first_row=8,
                        columns={"ahk_close":"G"},identity_column="A",name_column="B")
        document=mapped_xlsx(evidence[samples[0].doc_id],samples[0].doc_id,spec=table)
        self.assertEqual(check_document(document,samples[0].source),[])
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path=Path(directory)/f"{samples[0].doc_id}.pred.json"
            path.write_text(json.dumps(document))
            self.assertEqual(check(ROOT/"A3-Hackathon-Corpus",Path(directory)),0)
            document["rows"][0]["fields"]["ahk_close"]["raw_amount"]+=1
            path.write_text(json.dumps(document))
            self.assertEqual(check(ROOT/"A3-Hackathon-Corpus",Path(directory)),1)
            path.unlink()
            self.assertEqual(check(ROOT/"A3-Hackathon-Corpus",Path(directory)),1)

    def test_uncached_formula_is_not_a_blank_zero(self):
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        from carth.ingest import ingest

        ns={"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        original=DEMO/"f00_demo_01.xlsx"
        with TemporaryDirectory() as directory:
            source=Path(directory)/"formula.xlsx"
            with ZipFile(original) as src, ZipFile(source,"w") as dst:
                for item in src.infolist():
                    data=src.read(item.filename)
                    if item.filename=="xl/worksheets/sheet1.xml":
                        xml=ET.fromstring(data)
                        cell=xml.find(".//s:c[@r='G8']",ns)
                        for child in list(cell): cell.remove(child)
                        cell.attrib.pop("t",None)
                        ET.SubElement(cell,"{"+ns["s"]+"}f").text="SUM(C8:F8)"
                        data=ET.tostring(xml)
                    dst.writestr(item,data)
            evidence=ingest(source)
            table=TableSpec(sheet=evidence["sheets"][0]["sheet"],year=2025,unit="EUR",first_row=8,last_row=8,
                            columns={"ahk_close":"G"},identity_column="A",name_column="B")
            output=mapped_xlsx(evidence,"formula",spec=table)
            value=output["rows"][0]["fields"]["ahk_close"]
            self.assertIsNone(value["amount"])
            self.assertEqual(value["status"],"uncertain")
            self.assertEqual(check_document(output,source),[])
