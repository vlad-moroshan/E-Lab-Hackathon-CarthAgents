"""Validate corpus answer keys without reading or modifying their source documents.

Run from the project root: uv run carth validate-corpus [file-or-folder]
The default input is A3-Hackathon-Corpus in the current directory.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).with_name("corpus.schema.json")


def load_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker(formats=["date"]))


def validation_errors(document: dict, validator: Draft202012Validator) -> list[str]:
    """Schema errors plus cross-field invariants not expressible in standard JSON Schema."""
    errors = []
    for error in validator.iter_errors(document):
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        errors.append(f"{path}: {error.message}")
    if errors:
        return sorted(errors)

    meta = document["meta"]
    if not meta["doc_id"].startswith(meta["family"] + "_"):
        errors.append("/meta/doc_id: must begin with family + '_'")
    for i, row in enumerate(document["rows"]):
        path = f"/rows/{i}"
        if row["year"] not in meta["years"]:
            errors.append(f"{path}/year: is not listed in meta.years")
        if row["fields"].keys() != row["printed"].keys():
            errors.append(f"{path}/printed: keys must match fields exactly")
        flags = row.get("flags", {})
        if not flags.keys() <= row["fields"].keys() | {"*"}:
            errors.append(f"{path}/flags: flags must reference fields or '*'")
        pointer = row["pointer"]
        if "cells" in pointer and not pointer["cells"].keys() <= row["fields"].keys():
            errors.append(f"{path}/pointer/cells: must only reference fields in this row")
        if "bbox" in pointer:
            x0, top, x1, bottom = pointer["bbox"]
            if x0 > x1 or top > bottom:
                errors.append(f"{path}/pointer/bbox: coordinates must be ordered [x0, top, x1, bottom]")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=Path("A3-Hackathon-Corpus"))
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args(argv)
    validator = load_validator(args.schema)
    files = [args.input] if args.input.is_file() else sorted(args.input.rglob("*.key.json"))
    if not files:
        parser.error(f"no *.key.json files found in {args.input}")

    failed = rows = values = net_values = 0
    families: Counter[str] = Counter()
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            errors = validation_errors(document, validator)
            if not errors and path.name.endswith(".key.json"):
                if path.name.removesuffix(".key.json") != document["meta"]["doc_id"]:
                    errors.append("/meta/doc_id: does not match the answer-key filename")
        except (OSError, ValueError) as error:
            errors = [str(error)]
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for error in errors[:5]:
                print(f"  {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors")
            continue
        families[document["meta"]["family"]] += 1
        rows += len(document["rows"])
        values += sum(len(row["fields"]) for row in document["rows"])
        net_values += sum(len(row.get("net_fields", {})) for row in document["rows"])

    print(f"{len(files)} documents: {len(files) - failed} valid, {failed} invalid")
    print(f"{len(families)} families; {rows:,} rows; {values:,} amount fields; {net_values:,} net fields")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
