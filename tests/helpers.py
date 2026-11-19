"""Small helper that builds a correct raw invoice (as the LLM would return it)."""
import copy

GOOD_RAW = {
    "supplier_name": "Nordlys Konsult AB",
    "supplier_org_number": "556123-4567",
    "invoice_number": "2026-1001",
    "invoice_date": "2026-10-01",
    "due_date": "2026-10-31",
    "currency": "SEK",
    "lines": [
        {"description": "Konsulttimmar", "quantity": "10", "unit_price": "950,00", "line_total": "9 500,00"},
        {"description": "Fraktavgift", "quantity": "1", "unit_price": "250,00", "line_total": "250,00"},
    ],
    "total_excl_vat": "9 750,00",
    "vat_amount": "2 437,50",
    "total_incl_vat": "12 187,50",
}


def good_raw(**changes):
    raw = copy.deepcopy(GOOD_RAW)
    raw.update(changes)
    return raw
