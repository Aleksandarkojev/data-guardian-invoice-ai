"""Deterministic cleaning: turn messy strings into clean values.

No LLM here. The same input always gives the same output.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from tools.models import Issue

MONTHS = {
    # Swedish
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "okt": 10, "nov": 11, "dec": 12,
    # English (the ones that differ from Swedish)
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10,
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y.%m.%d")

CURRENCY_ALIASES = {
    "kr": "SEK", "kronor": "SEK", "sek": "SEK",
    "€": "EUR", "euro": "EUR", "eur": "EUR",
    "$": "USD", "usd": "USD",
    "nok": "NOK", "dkk": "DKK",
}


def parse_amount(value: Any) -> Decimal:
    """Turn '1 234,50 kr', '1,234.50' or '1.234,50' into Decimal('1234.50').

    Rule for a single separator: exactly 3 digits after it means thousands
    ('1,234' -> 1234), otherwise it is a decimal separator ('12,5' -> 12.5).
    """
    if value is None:
        raise ValueError("empty amount")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    text = str(value).replace("\u00a0", " ").strip()
    negative = text.startswith("-") or text.startswith("\u2212")
    text = re.sub(r"[^\d,.]", "", text)
    if not re.search(r"\d", text):
        raise ValueError(f"no number in {value!r}")

    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        text = _single_separator(text, ",")
    elif "." in text:
        text = _single_separator(text, ".")

    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"cannot read amount {value!r}") from exc
    return -number if negative else number


def _single_separator(text: str, sep: str) -> str:
    parts = text.split(sep)
    if len(parts) > 2:  # 1,234,567
        return text.replace(sep, "")
    if len(parts[1]) == 3:  # 1,234
        return text.replace(sep, "")
    return parts[0] + "." + parts[1]


def parse_date(value: Any) -> date:
    """Understand '2026-11-05', '05/11/2026' (day first), '5 nov 2026', '5 November 2026'."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError("empty date")

    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    match = re.fullmatch(r"(\d{1,2})\.?\s+([A-Za-z\u00e5\u00e4\u00f6\u00c5\u00c4\u00d6]+)\.?,?\s+(\d{4})", text)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(month_name.lower())
        if month:
            return date(int(year), month, int(day))
    raise ValueError(f"cannot read date {value!r}")


def normalize_currency(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    alias = CURRENCY_ALIASES.get(text.lower())
    if alias:
        return alias
    return text.upper() if len(text) == 3 else text


def normalize_org_number(value: Any) -> Optional[str]:
    """Swedish organisation number: 5560160680 -> 556016-0680."""
    text = _clean_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10:
        return f"{digits[:6]}-{digits[6:]}"
    return text


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _clean_date(value: Any, field: str, issues: list[Issue]) -> Optional[date]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return parse_date(value)
    except ValueError as exc:
        issues.append(Issue("unparseable_date", f"{field}: {exc}", field=field))
        return None


def _clean_amount(value: Any, field: str, issues: list[Issue]) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return parse_amount(value)
    except ValueError as exc:
        issues.append(Issue("unparseable_amount", f"{field}: {exc}", field=field))
        return None


def clean_raw(raw: dict) -> tuple[dict, list[Issue]]:
    """Take the LLM's raw dict and return clean values plus any problems."""
    issues: list[Issue] = []
    out: dict[str, Any] = {
        "supplier_name": _clean_text(raw.get("supplier_name")),
        "supplier_org_number": normalize_org_number(raw.get("supplier_org_number")),
        "invoice_number": _clean_text(raw.get("invoice_number")),
        "invoice_date": _clean_date(raw.get("invoice_date"), "invoice_date", issues),
        "due_date": _clean_date(raw.get("due_date"), "due_date", issues),
        "currency": normalize_currency(raw.get("currency")),
        "total_excl_vat": _clean_amount(raw.get("total_excl_vat"), "total_excl_vat", issues),
        "vat_amount": _clean_amount(raw.get("vat_amount"), "vat_amount", issues),
        "total_incl_vat": _clean_amount(raw.get("total_incl_vat"), "total_incl_vat", issues),
    }

    lines = []
    raw_lines = raw.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []
    for number, line in enumerate(raw_lines, start=1):
        if not isinstance(line, dict):
            issues.append(Issue("invalid_line", f"lines[{number}] is not an object", field=f"lines[{number}]"))
            continue
        lines.append(
            {
                "description": _clean_text(line.get("description")),
                "quantity": _clean_amount(line.get("quantity"), f"lines[{number}].quantity", issues),
                "unit_price": _clean_amount(line.get("unit_price"), f"lines[{number}].unit_price", issues),
                "line_total": _clean_amount(line.get("line_total"), f"lines[{number}].line_total", issues),
            }
        )
    out["lines"] = lines
    return out, issues
