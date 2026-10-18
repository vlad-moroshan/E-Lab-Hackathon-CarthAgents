"""Check extraction observations against source tokens and applicable row laws."""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from carth.ingest import ingest
from carth.ingest.pdf_text import text_in_bbox
from carth.output.validate import validation_errors
from carth.pipeline.amounts import parse_cents

LAWS = (
    ("ahk_close", {"ahk_open": 1, "zugang": 1, "abgang": -1, "umbuchung": 1}),
    ("kum_afa_close", {"kum_afa_open": 1, "afa_gj": 1, "afa_abgang": -1, "zuschreibung": -1}),
    ("bw_close", {"ahk_close": 1, "kum_afa_close": -1}),
    ("bw_prev", {"ahk_open": 1, "kum_afa_open": -1}),
    ("abgang_bw", {"abgang": 1, "afa_abgang": -1}),
)


def check_document(document: dict, source: Path, evidence: dict | None = None) -> list[str]:
    errors = validation_errors(document)
    if errors:
        return errors
    evidence = evidence if evidence is not None else ingest(source)
    cells = {(t["sheet"], t["cell"]): t for t in evidence["tokens"] if "cell" in t}
    pages = {p["page"]: p for p in evidence.get("pages", [])}
    sheets = {s["sheet"]: s for s in evidence.get("sheets", [])}
    for row in document["rows"]:
        observed = {f: v for f, v in row["fields"].items() if v["status"] == "observed"}
        for field, value in observed.items():
            label = f"{row['row_id']}/{field}"
            pointer = value["pointer"]
            if "sheet" in pointer:
                if pointer["sheet"] not in sheets:
                    errors.append(f"{label}: unknown source sheet")
                    continue
                token = cells.get((pointer["sheet"], pointer["cell"]))
                actual = token["value"] if token else None
                if actual is None:
                    ok = token is None and value["printed"] == "" and value["raw_amount"] == 0
                elif isinstance(actual, (int, float)) and not isinstance(actual, bool):
                    scale = 100000 if value["source_unit"] == "TEUR" else 100
                    try:
                        parsed = Decimal(str(actual)) * scale
                        ok = parsed.is_finite() and abs(parsed - value["raw_amount"]) < Decimal("0.000001")
                    except InvalidOperation:
                        ok = False
                else:
                    candidates = []
                    for decimal in (",", "."):
                        try:
                            candidates.append(parse_cents(actual, value["source_unit"], decimal))
                        except ValueError:
                            pass
                    ok = str(actual) == value["printed"] and value["raw_amount"] in candidates
                if not ok:
                    errors.append(f"{label}: source cell does not support raw value/text")
            else:
                page = pages.get(pointer["page"])
                x0, top, x1, bottom = pointer["bbox"]
                if page is None or x1 > page["width"] or bottom > page["height"]:
                    errors.append(f"{label}: pointer is outside the source page")
                    continue
                if not page["has_text"]:
                    errors.append(f"{label}: visual evidence needs OCR verification")
                    continue
                text = text_in_bbox(evidence["tokens"], pointer["page"], pointer["bbox"])
                printed = value["printed"]
                if (printed and printed not in text and printed not in text.replace(" ", "")) or (not printed and text.strip()):
                    errors.append(f"{label}: source box does not support printed text")
        for target, terms in LAWS:
            if target not in observed or not terms.keys() <= observed.keys():
                continue
            # Printed inconsistencies are valid extraction findings, not repaired amounts.
            reported = any(f.get("row_id") == row["row_id"] and f["code"] in {"non_tying", "source_inconsistency"}
                           and f.get("field", target) == target for f in document["findings"])
            difference = observed[target]["amount"] - sum(sign * observed[f]["amount"] for f, sign in terms.items())
            tolerance = sum(50000 for f in [target, *terms] if observed[f]["source_unit"] == "TEUR")
            if abs(difference) > tolerance and not reported:
                errors.append(f"{row['row_id']}/{target}: row law differs by {difference} cents")
    return errors
