"""Project extraction observations into the local scorer's legacy row format."""

from carth.output.validate import validation_errors


def for_scoring(document: dict) -> dict:
    """Keep GT/oracle predictions compatible; validate versioned extraction outputs."""
    if "schema_version" not in document:
        return document
    errors = validation_errors(document)
    if errors:
        raise ValueError("invalid extraction output: " + "; ".join(errors[:5]))
    rows = []
    for row in document["rows"]:
        # Net movements are retained in output but are outside the local score denominator.
        values = {name: value for name, value in row["fields"].items()
                  if name not in {"bew_ahk", "bew_wb"}}
        rows.append({
            **{key: value for key, value in row.items() if key != "fields"},
            "fields": {name: value["amount"] for name, value in values.items()},
            "printed": {name: value.get("printed", "") for name, value in values.items()},
            "pointers": {name: value["pointer"] for name, value in values.items() if "pointer" in value},
        })
    return {"meta": document["meta"], "rows": rows}
