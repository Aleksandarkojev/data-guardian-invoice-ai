"""Deterministic validation rules. The LLM never decides if data is valid; this code does."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import ValidationError

from tools.cleaning import clean_raw
from tools.models import Invoice, Issue

TOLERANCE = Decimal("0.01")
ALLOWED_VAT_RATES = (Decimal("0"), Decimal("0.06"), Decimal("0.12"), Decimal("0.25"))  # Swedish rates
ALLOWED_CURRENCIES = {"SEK", "EUR", "USD", "NOK", "DKK"}
MAX_AGE_DAYS = 5 * 365


def close(a: Decimal, b: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def luhn_check_digit(first_nine: str) -> str:
    """Check digit that makes a 10-digit Swedish org number pass the Luhn test."""
    total = 0
    for index, char in enumerate(reversed(first_nine + "0")):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def is_valid_org_number(value: str) -> bool:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 10:
        return False
    return luhn_check_digit(digits[:9]) == digits[9]


def check_rules(
    invoice: Invoice,
    today: Optional[date] = None,
    seen: Optional[set] = None,
) -> list[Issue]:
    """Run all business rules. Returns a list of issues (empty list = valid)."""
    today = today or date.today()
    issues: list[Issue] = []

    # Each line: quantity x unit price = line total
    for number, line in enumerate(invoice.lines, start=1):
        if not close(line.quantity * line.unit_price, line.line_total):
            issues.append(Issue(
                "line_total_mismatch",
                f"Line {number}: {line.quantity} x {line.unit_price} is not {line.line_total}",
                field=f"lines[{number}].line_total",
            ))

    # Lines add up to the total without VAT
    lines_sum = sum((line.line_total for line in invoice.lines), Decimal("0"))
    if not close(lines_sum, invoice.total_excl_vat):
        issues.append(Issue(
            "lines_sum_mismatch",
            f"Lines add up to {lines_sum}, but total excl. VAT is {invoice.total_excl_vat}",
            field="total_excl_vat",
        ))

    # Total without VAT + VAT = total with VAT
    if not close(invoice.total_excl_vat + invoice.vat_amount, invoice.total_incl_vat):
        issues.append(Issue(
            "total_mismatch",
            f"{invoice.total_excl_vat} + {invoice.vat_amount} is not {invoice.total_incl_vat}",
            field="total_incl_vat",
        ))

    # VAT should match a normal Swedish rate
    rate_ok = any(
        close(invoice.vat_amount, (invoice.total_excl_vat * rate).quantize(Decimal("0.01")), Decimal("0.02"))
        for rate in ALLOWED_VAT_RATES
    )
    if not rate_ok:
        issues.append(Issue(
            "vat_rate_unusual",
            f"VAT {invoice.vat_amount} on {invoice.total_excl_vat} is not 0, 6, 12 or 25 percent",
            field="vat_amount",
        ))

    # Dates
    if invoice.invoice_date > today:
        issues.append(Issue("date_in_future", f"Invoice date {invoice.invoice_date} is in the future",
                            field="invoice_date"))
    if invoice.invoice_date < today - timedelta(days=MAX_AGE_DAYS):
        issues.append(Issue("date_too_old", f"Invoice date {invoice.invoice_date} is older than 5 years",
                            field="invoice_date"))
    if invoice.due_date is not None and invoice.due_date < invoice.invoice_date:
        issues.append(Issue("due_before_invoice", "Due date is before the invoice date", field="due_date"))

    # Currency
    if invoice.currency not in ALLOWED_CURRENCIES:
        issues.append(Issue("currency_not_allowed", f"Currency {invoice.currency} is not in the allowed list",
                            field="currency"))

    # Organisation number (only if present)
    if invoice.supplier_org_number and not is_valid_org_number(invoice.supplier_org_number):
        issues.append(Issue("org_number_invalid", f"Org number {invoice.supplier_org_number} fails the Luhn check",
                            field="supplier_org_number"))

    # Duplicate inside this batch (the database also has a UNIQUE key as a second safety net)
    if seen is not None and (invoice.supplier_name, invoice.invoice_number) in seen:
        issues.append(Issue("duplicate_invoice",
                            f"{invoice.supplier_name} / {invoice.invoice_number} was already processed",
                            field="invoice_number", retryable=False))
    return issues


def build_invoice(
    raw: dict,
    today: Optional[date] = None,
    seen: Optional[set] = None,
) -> tuple[Optional[Invoice], list[Issue]]:
    """clean -> typed model -> business rules.

    Returns (invoice, issues). The invoice is None only when the data is too broken
    to build (missing required fields, unreadable numbers).
    """
    cleaned, issues = clean_raw(raw)
    try:
        invoice = Invoice.model_validate(cleaned)
    except ValidationError as exc:
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            issues.append(Issue("missing_or_invalid_field", f"{location}: {error['msg']}", field=location))
        return None, issues
    issues.extend(check_rules(invoice, today=today, seen=seen))
    return invoice, issues
