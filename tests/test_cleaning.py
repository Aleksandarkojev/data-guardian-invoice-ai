from datetime import date
from decimal import Decimal

import pytest

from tools.cleaning import normalize_currency, normalize_org_number, parse_amount, parse_date


@pytest.mark.parametrize("text, expected", [
    ("1 234,50 kr", Decimal("1234.50")),
    ("1\u00a0234,50", Decimal("1234.50")),
    ("1,234.50", Decimal("1234.50")),
    ("1.234,50", Decimal("1234.50")),
    ("1234.5", Decimal("1234.5")),
    ("12,5", Decimal("12.5")),
    ("1,234", Decimal("1234")),
    ("1 234 567,89", Decimal("1234567.89")),
    ("-250,00 kr", Decimal("-250.00")),
    (99, Decimal("99")),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("bad", ["abc", "", None, "kr"])
def test_parse_amount_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


@pytest.mark.parametrize("text, expected", [
    ("2026-11-05", date(2026, 11, 5)),
    ("05/11/2026", date(2026, 11, 5)),      # day first
    ("05.11.2026", date(2026, 11, 5)),
    ("5 nov 2026", date(2026, 11, 5)),
    ("5 november 2026", date(2026, 11, 5)),
    ("5 November 2026", date(2026, 11, 5)),
    ("17 maj 2026", date(2026, 5, 17)),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-40", "", None])
def test_parse_date_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_date(bad)


def test_currency():
    assert normalize_currency("kr") == "SEK"
    assert normalize_currency("sek") == "SEK"
    assert normalize_currency("€") == "EUR"
    assert normalize_currency(None) is None


def test_org_number():
    assert normalize_org_number("5560160680") == "556016-0680"
    assert normalize_org_number("556016-0680") == "556016-0680"
    assert normalize_org_number("") is None
