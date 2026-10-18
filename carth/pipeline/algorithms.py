"""Small starting algorithms; all inputs are source evidence, never answer keys."""

from dataclasses import dataclass, field

from carth.pipeline.amounts import parse_cents


def abstain(evidence: dict, doc_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "meta": {"doc_id": doc_id, "format": "xlsx" if evidence["kind"] == "xlsx" else "pdf", "years": []},
        "rows": [],
        "findings": [{"code": "no_extraction", "severity": "warning", "message": "No algorithm has identified a supported schedule."}],
    }


@dataclass(frozen=True)
class TableSpec:
    """Explicit layout configuration, supplied after inspecting the source evidence."""

    sheet: str
    year: int
    unit: str
    first_row: int
    columns: dict[str, str]
    identity_column: str
    name_column: str
    last_row: int | None = None
    level: str = "asset"
    decimal: str = ","
    magnitude_fields: frozenset[str] = field(default_factory=frozenset)


def mapped_xlsx(evidence: dict, doc_id: str, *, spec: TableSpec) -> dict:
    """Extract explicitly mapped leaf rows; other layouts abstain. No filename rules."""
    if evidence["kind"] != "xlsx":
        return abstain(evidence, doc_id)
    sheets = {s["sheet"]: s for s in evidence["sheets"]}
    if spec.sheet not in sheets:
        raise ValueError(f"unknown sheet: {spec.sheet}")
    cells = {t["cell"]: t for t in evidence["tokens"] if t["sheet"] == spec.sheet}
    result = abstain(evidence, doc_id)
    result["meta"].update(years=[spec.year], unit=spec.unit)
    result["findings"] = []
    for index in range(spec.first_row, (spec.last_row or sheets[spec.sheet]["max_row"]) + 1):
        identity = cells.get(f"{spec.identity_column}{index}")
        if identity is None or not any(f"{col}{index}" in cells for col in spec.columns.values()):
            continue  # headings, totals without an identity and empty rows are outside this explicit leaf mapping
        row = {"row_id": f"{spec.sheet}!{index}", "kind": "asset", "level": spec.level,
               "year": spec.year, "fields": {}}
        id_field = {"asset": "asset_no", "account": "account", "class": "class", "bilanzposition": "position"}[spec.level]
        row[id_field] = identity["text"]
        name = cells.get(f"{spec.name_column}{index}")
        if name is not None:
            row["name"] = name["text"]
        for semantic, column in spec.columns.items():
            address = f"{column}{index}"
            token = cells.get(address)
            pointer = {"sheet": spec.sheet, "cell": address}
            printed = token["text"] if token else ""
            try:
                raw = parse_cents(token["value"], spec.unit, spec.decimal) if token else 0
                row["fields"][semantic] = {"amount": abs(raw) if semantic in spec.magnitude_fields else raw,
                    "status": "observed", "raw_amount": raw, "printed": printed, "source_unit": spec.unit, "pointer": pointer}
            except ValueError as error:
                row["fields"][semantic] = {"amount": None, "status": "uncertain", "reason": str(error),
                                           "printed": printed, "pointer": pointer}
        result["rows"].append(row)
    if not result["rows"]:
        result["findings"].append({"code": "no_mapped_rows", "severity": "warning", "message": "No leaf rows match the supplied table mapping."})
    return result
