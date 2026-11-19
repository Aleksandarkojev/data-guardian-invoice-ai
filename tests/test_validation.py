from datetime import date

from tests.helpers import good_raw
from tools.validation import build_invoice, is_valid_org_number, luhn_check_digit

TODAY = date(2026, 11, 19)


def codes(issues):
    return {issue.code for issue in issues}


def test_good_invoice_has_no_issues():
    invoice, issues = build_invoice(good_raw(), today=TODAY)
    assert issues == []
    assert str(invoice.total_incl_vat) == "12187.50"
    assert invoice.invoice_date == date(2026, 10, 1)


def test_org_number_helpers():
    assert luhn_check_digit("556123456") == "7"
    assert is_valid_org_number("556123-4567") is True
    assert is_valid_org_number("556016-0680") is True      # a real, valid number
    assert is_valid_org_number("556016-0681") is False
    assert is_valid_org_number("123") is False


def test_invalid_org_number_is_reported():
    _, issues = build_invoice(good_raw(supplier_org_number="556123-4568"), today=TODAY)
    assert codes(issues) == {"org_number_invalid"}


def test_total_mismatch():
    _, issues = build_invoice(good_raw(total_incl_vat="12 287,50"), today=TODAY)
    assert "total_mismatch" in codes(issues)


def test_line_total_mismatch():
    raw = good_raw()
    raw["lines"][0]["line_total"] = "9 600,00"
    _, issues = build_invoice(raw, today=TODAY)
    assert "line_total_mismatch" in codes(issues)
    assert "lines_sum_mismatch" in codes(issues)


def test_lines_sum_mismatch():
    _, issues = build_invoice(good_raw(total_excl_vat="9 000,00", vat_amount="2 250,00",
                                       total_incl_vat="11 250,00"), today=TODAY)
    assert codes(issues) == {"lines_sum_mismatch"}


def test_unusual_vat_rate():
    _, issues = build_invoice(good_raw(vat_amount="1 950,00", total_incl_vat="11 700,00"), today=TODAY)
    assert codes(issues) == {"vat_rate_unusual"}


def test_dates():
    assert "date_in_future" in codes(build_invoice(good_raw(invoice_date="2027-01-01", due_date="2027-02-01"),
                                                   today=TODAY)[1])
    assert "date_too_old" in codes(build_invoice(good_raw(invoice_date="2015-01-01", due_date="2015-02-01"),
                                                 today=TODAY)[1])
    assert "due_before_invoice" in codes(build_invoice(good_raw(due_date="2026-09-01"), today=TODAY)[1])


def test_currency_not_allowed():
    _, issues = build_invoice(good_raw(currency="XYZ"), today=TODAY)
    assert "currency_not_allowed" in codes(issues)


def test_missing_required_field_gives_no_invoice():
    raw = good_raw()
    raw["invoice_number"] = None
    invoice, issues = build_invoice(raw, today=TODAY)
    assert invoice is None
    assert "missing_or_invalid_field" in codes(issues)


def test_unreadable_amount():
    invoice, issues = build_invoice(good_raw(total_excl_vat="abc"), today=TODAY)
    assert invoice is None
    assert "unparseable_amount" in codes(issues)


def test_no_lines():
    invoice, issues = build_invoice(good_raw(lines=[]), today=TODAY)
    assert invoice is None
    assert "missing_or_invalid_field" in codes(issues)


def test_duplicate_in_batch_is_not_retryable():
    seen = {("Nordlys Konsult AB", "2026-1001")}
    _, issues = build_invoice(good_raw(), today=TODAY, seen=seen)
    assert codes(issues) == {"duplicate_invoice"}
    assert issues[0].retryable is False
