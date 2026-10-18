"""Printed amount text -> exact integer, and glued amounts -> candidate splits. Pure functions, no guessing.

Every style the corpus prints (core.fmt): 1.234,56 · 1234,56 · 1.234,56- · -1.234,56 · (1.234,56) · 1,234.56 ·
TEUR 1.235 · zeros as "0,00", "0", "-". Amounts carry 2 decimals or none, never 1 or 3: so a final separator followed
by exactly 2 digits is the decimal mark, and every other group has 3 digits. That makes "1.235" a TEUR integer, not
1,235 EUR, and rejects dates (31.12.2025), account numbers with dots, and the like.

OCR mode also accepts a decimal mark read as the group mark ("314.602.06" for "314.602,06"): the digits are
intact, the row laws confirm the value later.

    python -m carth.numbers        runs the examples below
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BODY = re.compile(r"^(\d{1,3}(?:([.,' ])\d{3})?(?:\2\d{3})*|\d+)(?:([.,])(\d{2}))?$")  # one group mark per number


@dataclass(frozen=True)
class Amount:
    mantissa: int  # signed, in units of the last printed digit: 1.234,56 -> 123456; TEUR 1.235 -> 1235
    decimals: int  # 2 or 0
    neg: bool
    style: str  # sign style: "plain" | "lead" | "trail" | "paren" | "dash" (a lone "-" = zero)
    mark: str = ""  # decimal mark as printed ("," or "."), "" without decimals

    def cents(self, unit: str = "EUR") -> int:
        """Amount in cents. TEUR: printed thousands (no decimals) -> cents; a TEUR doc with 2 decimals is rare."""
        scale = {"EUR": 100, "TEUR": 100_000}[unit]
        return self.mantissa * scale // (100 if self.decimals == 2 else 1)


def parse_amount(text: str, ocr: bool = False) -> Amount | None:
    s = text.strip().replace("−", "-").replace("\u00a0", " ").replace("\u202f", " ") if text else ""
    if s in ("-", "–"):
        return Amount(0, 0, False, "dash")
    style, neg = "plain", False
    if s.startswith("(") and s.endswith(")"):
        s, style, neg = s[1:-1], "paren", True
    elif s.endswith("-"):
        s, style, neg = s[:-1], "trail", True
    elif s.startswith("-"):
        s, style, neg = s[1:], "lead", True
    elif s.startswith("+"):
        s = s[1:]
    m = _BODY.match(s)
    if not m:
        return None
    whole, group, dec, cents = m.groups()
    if dec and group and dec == group and not ocr:  # 1.234.56 is not an amount, unless OCR misread the comma
        return None
    if not dec and not group and len(whole) > 1 and whole.startswith("0"):
        return None  # 0027, 027001: identifiers, not amounts
    digits = whole.replace(".", "").replace(",", "").replace("'", "").replace(" ", "")
    v = int(digits + (cents or ""))
    return Amount(-v if neg else v, 2 if dec else 0, neg, style, dec or "")


def split_glued(text: str, ocr: bool = False) -> list[tuple[Amount, Amount, str, str]]:
    """'12.977,004.076,11' -> [(12.977,00, 4.076,11)]. Every split where both halves parse as amounts with the
    same number of decimals; the row laws pick among several candidates."""
    out = []
    s = text.strip()
    for i in range(1, len(s)):
        a, b = parse_amount(s[:i], ocr), parse_amount(s[i:], ocr)
        if a and b and a.decimals == b.decimals == 2 and a.mark == b.mark and "dash" not in (a.style, b.style):
            out.append((a, b, s[:i], s[i:]))
    return out


def source_amount(text: str, *, amount_column: bool, unit: str = "EUR", signed: bool = False,
                  ocr: bool = False) -> tuple[int | None, str | None]:
    """Extraction gate: syntax alone cannot classify an ID/year as money.

    OCR punctuation repairs and glued alternatives need separate source review; arithmetic cannot authorize them.
    """
    if not amount_column:
        return None, "not an identified amount column"
    a = parse_amount(text)
    if a is None:
        return None, "ambiguous OCR punctuation" if ocr and parse_amount(text, ocr=True) else "unreadable or glued amount"
    cents = a.cents(unit)
    return (cents if signed else abs(cents)), None


def _selfcheck() -> None:
    P = parse_amount
    assert P("1.234,56").cents() == 123456 and P("1234,56").cents() == 123456
    assert P("1.234,56-").cents() == -123456 and P("-1.234,56").cents() == -123456
    assert P("(1.234,56)").cents() == -123456 and P("1,234.56").cents() == 123456
    assert P("1.235").cents("TEUR") == 123_500_000 and P("0").cents("TEUR") == 0 and P("-1.235").neg
    assert P("0,00").cents() == 0 and P("-").cents() == 0 and P("1,00").cents() == 100
    assert P("11.430.820,91").cents() == 1143082091
    for bad in ("31.12.2025", "31.12.25", "2025-12-31", "12/2025", "0027", "027001", "1.234.56", "1,2", "1.2345",
                "abc", "", "EUR", "Nr. 13"):
        assert P(bad) is None, bad
    assert P("314.602.06", ocr=True).cents() == 31460206 and P("314.602.06") is None
    assert [(a.cents(), b.cents()) for a, b, *_ in split_glued("12.977,004.076,11")] == [(1297700, 407611)]
    assert [(a.cents(), b.cents()) for a, b, *_ in split_glued("1.295,0618.130,90")] == [(129506, 1813090)]
    assert len(split_glued("1,00-2,00")) == 2  # "1,00-|2,00" and "1,00|-2,00": the laws decide
    print("numbers self-check OK")


if __name__ == "__main__":
    _selfcheck()
