"""Deterministic money parsing; no model-generated financial values."""

from decimal import Decimal
import math
import re


def parse_cents(value, unit: str = "EUR", decimal: str = ",") -> int:
    if unit not in {"EUR", "TEUR"} or decimal not in {",", "."}:
        raise ValueError("unsupported unit or decimal separator")
    if isinstance(value, bool) or value is None:
        raise ValueError("missing/non-numeric amount")
    if isinstance(value, (float, int)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite amount")
        number = Decimal(str(value))
    else:
        text = str(value).strip().replace("\u00a0", " ")
        if text == "-":
            return 0
        sign = 1
        if text.startswith("(") and text.endswith(")"):
            sign, text = -1, text[1:-1]
        elif text.endswith("-"):
            sign, text = -1, text[:-1]
        elif text.startswith("-"):
            sign, text = -1, text[1:]
        elif text.startswith("+"):
            text = text[1:]
        thousands = "." if decimal == "," else ","
        pattern = rf"(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(thousands)}[0-9]{{3}})+)(?:{re.escape(decimal)}[0-9]+)?"
        if not re.fullmatch(pattern, text):
            raise ValueError(f"ambiguous or invalid amount: {value!r}")
        number = Decimal(text.replace(thousands, "").replace(decimal, ".")) * sign
    cents = number * (100000 if unit == "TEUR" else 100)
    # Permit only insignificant binary-floating serialization residue, never round visible fractions of a cent.
    rounded = cents.to_integral_value()
    if not cents.is_finite() or abs(cents - rounded) > Decimal("0.000001"):
        raise ValueError("amount is not an integer number of cents")
    return int(rounded)
