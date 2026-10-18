"""Validate extraction outputs without reading ground truth or source documents."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).with_name("extraction.schema.json")


def load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker(formats=["date"]))


def validation_errors(document: dict, validator: Draft202012Validator | None = None) -> list[str]:
    validator = validator if validator is not None else load_validator()
    errors = [f"/{'/'.join(map(str, e.absolute_path))}: {e.message}"
              for e in validator.iter_errors(document)]
    if errors:
        return sorted(errors)

    meta, rows, findings = document["meta"], document["rows"], document["findings"]
    by_id = {}

    def pointer_errors(pointer: dict, path: str):
        if (meta["format"] == "xlsx") != ("sheet" in pointer):
            errors.append(f"{path}: pointer type does not match meta.format")
        if "bbox" in pointer:
            x0, top, x1, bottom = pointer["bbox"]
            if not all(math.isfinite(v) for v in pointer["bbox"]) or x0 >= x1 or top >= bottom:
                errors.append(f"{path}/bbox: must be finite with positive width and height")
        if "cell" in pointer:
            address = pointer["cell"]
            column = 0
            for char in address:
                if not char.isalpha():
                    break
                column = column * 26 + ord(char) - ord("A") + 1
            row = int("".join(c for c in address if c.isdigit()))
            if column > 16384 or row > 1048576:
                errors.append(f"{path}/cell: outside Excel worksheet bounds")

    for i, row in enumerate(rows):
        path = f"/rows/{i}"
        if row["row_id"] in by_id:
            errors.append(f"{path}/row_id: duplicate row ID")
        by_id[row["row_id"]] = row
        if row["year"] is not None and row["year"] not in meta["years"]:
            errors.append(f"{path}/year: is not listed in meta.years")
        if not row["fields"] and not any(f.get("row_id") == row["row_id"] for f in findings):
            errors.append(f"{path}/fields: empty row requires a row finding")
        for name, value in row["fields"].items():
            vpath = f"{path}/fields/{name}"
            if "pointer" in value:
                pointer_errors(value["pointer"], f"{vpath}/pointer")
            if value["status"] == "observed":
                allowed = {value["raw_amount"]}
                if name not in {"umbuchung", "bew_ahk", "bew_wb"}:
                    allowed.add(abs(value["raw_amount"]))
                if value["amount"] not in allowed:
                    errors.append(f"{vpath}: amount is inconsistent with raw cents and field sign semantics")
            if value["status"] == "observed" and not value["printed"].strip():
                if value["amount"] != 0 or value["raw_amount"] != 0:
                    errors.append(f"{vpath}: a blank observed amount must be zero")

    for i, finding in enumerate(findings):
        path = f"/findings/{i}"
        if "pointer" in finding:
            pointer_errors(finding["pointer"], f"{path}/pointer")
        if "row_id" in finding:
            row = by_id.get(finding["row_id"])
            if row is None:
                errors.append(f"{path}/row_id: unknown row ID")
            elif "field" in finding and finding["field"] not in row["fields"]:
                errors.append(f"{path}/field: field is not present in the referenced row")

    if (not rows or not meta["years"]) and not any("row_id" not in f for f in findings):
        errors.append("/findings: empty rows or unknown reporting years require a document finding")
    return sorted(errors)


def reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=Path("out/pred"))
    args = parser.parse_args(argv)
    files = [args.input] if args.input.is_file() else sorted(args.input.rglob("*.pred.json"))
    if not files:
        parser.error(f"no *.pred.json files found in {args.input}")
    validator = load_validator()
    failed = 0
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
            errors = validation_errors(document, validator)
            if not errors and path.name.endswith(".pred.json"):
                if path.name.removesuffix(".pred.json") != document["meta"]["doc_id"]:
                    errors.append("/meta/doc_id: does not match the prediction filename")
        except (OSError, ValueError) as error:
            errors = [str(error)]
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for error in errors:
                print(f"  {error}")
    print(f"{len(files)} documents: {len(files) - failed} valid, {failed} invalid")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
