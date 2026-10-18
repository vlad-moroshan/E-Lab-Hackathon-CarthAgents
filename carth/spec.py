"""Stage 3 (M6): layout spec from an LLM. The model reads the document's lines (amounts masked) and says what the
structure MEANS; it returns references only (column / band numbers, record line offsets, regexes over masked line
text, page numbers), never an amount. Code (M7) applies the spec and copies every figure from the tokens.

Prompt view of a PDF line:   L12 g0.35 i0: 27001 Office-Lizenzen Typ S146 #b0 #b4 #-b5 1,00?  ->  every 2-decimal
amount is "#b<band>" ("#-b<band>" if printed negative, "#b?" outside any band); integers are shown with their band
("7150@b0"); dates as DATE. xlsx rows: "R12 [hidden]: A=Inventar-Nr | F=#c6 | …" with c<column number>.

    python -m carth.spec out/tokens/f00_demo_02.json [--model gpt-6.1-sol]     prints the spec (cached in out/spec/)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from carth.layout import layout
from carth.numbers import parse_amount

DEFAULT_MODEL = os.environ.get("CARTH_MODEL", "gpt-6-astra")  # best of 4 on the 10-doc sample (eval/spec_metrics.py)
CACHE = Path("out/spec")
FIELDS = ("ahk_open", "zugang", "abgang", "umbuchung", "zuschreibung", "ahk_close", "kum_afa_open", "afa_gj",
          "afa_abgang", "kum_afa_close", "bw_close", "bw_prev", "abgang_bw", "bew_ahk", "bew_wb", "ignore")
FieldName = Literal[FIELDS]  # type: ignore[valid-type]
MAX_LINES_PER_PAGE, MAX_PAGES, MAX_ROWS = 45, 6, 140


# ---------------------------------------------------------------------------------------------------- schema


class FieldMap(BaseModel):
    line: int = Field(description="0-based line inside the record (0 = the record's first line)")
    band: int = Field(description="band number (PDF) or column number (xlsx) holding the amount")
    field: FieldName = Field(description="canonical field; 'ignore' for amount columns that are not a target field")


class IdRule(BaseModel):
    field: Literal["asset_no", "sub_no", "class", "account", "position"]
    regex: str = Field(description="Python regex with ONE capture group returning the code exactly as printed "
                                   "(e.g. '0027', '210004', '1000'), searched in the masked line text")
    scope: Literal["record", "heading"] = Field(description="record: the first line of each record / subtotal; "
                                                            "heading: heading lines whose code applies to the rows below")


class RowRole(BaseModel):
    regex: str = Field(description="Python regex searched in the masked line text (case-insensitive)")
    role: Literal["class_subtotal", "account_subtotal", "position_subtotal", "grand_total", "carry_over", "heading",
                  "header", "noise"]


class Section(BaseModel):
    name: str
    pages: list[int] = Field(description="PDF pages (1-based) of this section; for xlsx: []")
    sheet: str | None = Field(description="xlsx sheet name, else null")
    year: int | None = Field(description="fiscal year (year of the period end) reported in this section")
    unit: Literal["EUR", "TEUR"]
    granularity: Literal["asset", "account", "class", "position"] = Field(
        description="what one leaf record is: a single asset, a ledger account, an asset class, a balance-sheet line")
    gross_or_net: Literal["gross", "net"] = Field(description="net = starts from prior book value (abgang_bw)")
    record_lines: int = Field(description="printed lines per record (1 for one line per asset, 3 or 4 for blocks)")
    record_start: str = Field(description="Python regex on masked line text that matches the FIRST line of every record "
                                          "and subtotal block, and no other line")
    fields: list[FieldMap]
    roles: list[RowRole]
    ids: list[IdRule] = Field(description="how to read each printed identity code of a row: the asset number (and "
                                          "sub-number) of asset rows, the class / account / position code of leaf "
                                          "rows at that granularity, and codes printed on heading lines")
    year_columns_note: str = Field(description="free text: anything unusual (two years, repeated values, hidden "
                                               "columns to ignore, units)")


class Spec(BaseModel):
    doc_type: str
    is_asset_schedule: bool
    noise_pages: list[int]
    sections: list[Section]


SYSTEM = """You read German fixed-asset schedules (Anlagenspiegel / Anlagengitter / Anlagenverzeichnis) and describe
their LAYOUT so that code can copy the numbers. You never output an amount: all amounts are already masked as
#b<band> (#-b<band> = printed negative). You answer with band numbers, line offsets, regexes and page numbers only.

Canonical fields (gross roll-forward): ahk_open (AHK/Anschaffungskosten at start, "Stand 01.01.", "AHK GJ-Beg",
"Anfangsstand"), zugang (additions), abgang (disposals at cost), umbuchung (transfers, signed), zuschreibung
(write-ups), ahk_close (AHK at end, "aktuelle AHK", "Endstand"), kum_afa_open (accumulated depreciation at start),
afa_gj (depreciation of the year), afa_abgang (depreciation on disposals), kum_afa_close (accumulated depreciation at
end), bw_close (book value at end, "Buchwert 31.12.", "Restbuchwert"), bw_prev (book value prior year / at start),
abgang_bw (net layouts: disposals at book value). SAP net columns: bew_ahk ("Bew AnschWert"), bew_wb ("Bew Wertber").
Use 'ignore' for amount columns that are none of these (e.g. aktivierte Zinsen, Sonder-AfA, percentages, ND rates).

Rules:
- A record may span several printed lines (blocks): give record_lines and a field map per (line, band).
- record_start must match the first line of every record AND of every subtotal/total block in the section.
- roles: regexes that identify subtotal / total / carry-over (Übertrag) / heading / repeated page header lines.
- Two fiscal years or two tables = two sections. Cover letters, blank pages, unrelated reports go to noise_pages.
- If the document is not a fixed-asset schedule (trial balance, P&L, balance sheet), set is_asset_schedule=false.
- year: the fiscal year of the period END of the section (e.g. "01.07.2024 bis 30.06.2025" -> 2025). Never null when a
  period or report date is printed. A print / creation date is not the period.
- Roles for sum lines: class_subtotal = sum of an asset class / group block; account_subtotal = sum per ledger account
  (Konto, Bestandskonto) where accounts are a separate level; position_subtotal = sum per balance-sheet position
  (numbered position, roman-numeral group or 7-digit SAP Bilanzposition); grand_total = sum of everything;
  carry_over = Übertrag / carried-forward running sum at page breaks. heading = a label line without amounts.
- ids: identity codes as printed (single words such as '0027', '210004', '1000', '2102100'), one capture group each.
  Name the code by what it is in German accounting: account = ledger account number (Konto, Sachkonto, Bestandskonto;
  SKR03/SKR04 fixed-asset accounts are 3-4 digits, often with a leading zero, e.g. 027, 0027, 0210); class = asset class
  code (Anlagenklasse / Klasse, e.g. 1000, 3000, L1000); position = balance-sheet position (A.II.1, roman / numbered
  group, 7-digit SAP Bilanzposition); asset_no = inventory / asset number (Anlage, Inventar-Nr.).
  Regexes are matched against the line as shown AND against its plain text (cell values only, no "A14=" coordinates,
  no "@b" band tags), so write them for the plain text.
  Asset rows need asset_no (and sub_no where printed). Leaf rows at class / account / position level need their own
  code. Codes printed on heading lines (e.g. "0027 EDV-Software") are given with scope "heading"."""


# ---------------------------------------------------------------------------------------------------- prompt view


def _cell(tok: dict, band, xlsx: bool) -> str:
    t, s = tok["type"], tok["text"]
    if t == "amount":
        neg = parse_amount(s) is not None and parse_amount(s).neg if not xlsx else (tok.get("value") or 0) < 0
        tag = f"c{band}" if xlsx else f"b{band if band is not None else '?'}"
        return f"#{'-' if neg else ''}{tag}"
    if t == "glued":
        return f"#GLUED@b{band if band is not None else '?'}"
    if t == "date":
        return s  # dates are not financial figures: the model needs them for the fiscal year
    if t == "int" and band is not None:
        return f"{s}@b{band}"
    return s


def render(lay: dict) -> str:
    toks, out = lay["tokens"], []
    if lay["kind"] == "xlsx":
        for sh in lay["sheets"]:
            out.append(f"=== sheet {sh['sheet']!r} ({sh['state']}); hidden columns: {sh['hidden_cols']}")
            for ln in sh["lines"][:MAX_ROWS]:
                cells = " | ".join(f"{toks[c['tid']]['cell']}={_cell(toks[c['tid']], c['band'], True)}" for c in ln["cells"])
                out.append(f"R{ln['row']}{' [hidden]' if ln['hidden'] else ''}: {cells}")
        return "\n".join(out)
    pages = lay["pages"]
    keep = pages[:MAX_PAGES] + ([pages[-1]] if len(pages) > MAX_PAGES else [])
    for pg in keep:
        out.append(f"=== page {pg['page']} (bands: " + ", ".join(f"b{b['id']}@x{b['x1']:.0f}" for b in pg["bands"]) + ")")
        lines = pg["lines"]
        show = lines if len(lines) <= MAX_LINES_PER_PAGE else lines[:MAX_LINES_PER_PAGE - 8] + [None] + lines[-8:]
        for ln in show:
            if ln is None:
                out.append("…")
                continue
            body = " ".join(_cell(toks[c["tid"]], c["band"], False) for c in ln["cells"])
            gap = "" if ln["gap_above"] is None else f" g{ln['gap_above']:.1f}"
            out.append(f"L{ln['id'].split('l')[-1]}{gap} i{ln['indent']:.0f}: {body}")
    if len(pages) > len(keep):
        out.append(f"(document has {len(pages)} pages; pages {len(keep)}..{len(pages) - 1} not shown follow the same layout)")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------- model call


def load_env(path: Path = Path(".env")) -> None:
    """KEY=VALUE lines into os.environ (never printed); existing variables win."""
    if path.exists():
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                os.environ.setdefault(m.group(1), m.group(2).strip("'\""))


def infer(lay: dict, model: str = DEFAULT_MODEL, cache: Path | None = CACHE) -> tuple[Spec, dict]:
    """(spec, info) for a layout; cached by model + prompt hash. info: model, seconds, token usage, cache hit."""
    import time

    view = render(lay)
    h = hashlib.sha256(f"{model}\n{SYSTEM}\n{view}".encode()).hexdigest()[:16]
    cp = cache / f"{h}.json" if cache else None
    if cp and cp.exists():
        d = json.loads(cp.read_text())
        return Spec.model_validate(d["spec"]), {**d["info"], "cached": True}
    load_env()
    from openai import OpenAI

    t0 = time.time()
    r = OpenAI().responses.parse(model=model, input=[{"role": "system", "content": SYSTEM},
                                                     {"role": "user", "content": view}], text_format=Spec)
    spec = r.output_parsed
    info = {"model": model, "seconds": round(time.time() - t0, 1), "input_tokens": r.usage.input_tokens,
            "output_tokens": r.usage.output_tokens, "prompt_chars": len(view), "cached": False}
    if cp:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps({"spec": spec.model_dump(), "info": info}, ensure_ascii=False, indent=1))
    return spec, info


if __name__ == "__main__":
    import argparse

    from carth import ingest

    ap = argparse.ArgumentParser()
    ap.add_argument("tokens", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--view", action="store_true", help="print the prompt view only (no API call)")
    a = ap.parse_args()
    lay = layout(ingest.load(a.tokens))
    if a.view:
        print(render(lay))
        sys.exit(0)
    spec, info = infer(lay, a.model)
    print(json.dumps(spec.model_dump(), ensure_ascii=False, indent=1))
    print(info, file=sys.stderr)
