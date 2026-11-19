"""Make fake invoices (PDF) and the correct answers (JSON), so you can measure accuracy.

Run:  python -m generator.make_invoices --count 50 --seed 42

Output:
  data/invoices/INV-0001.pdf   <- what the pipeline reads
  data/truth/INV-0001.json     <- what the correct answer is (including deliberate flaws)

About 15 percent of the invoices get a deliberate flaw. The truth file keeps the value
that is printed in the PDF and lists the issue codes that validation should find.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from tools.validation import luhn_check_digit

SUPPLIER_BASES = [
    ("Nordlys Konsult AB", "556123456"),
    ("Skåne Kontorsvaror AB", "556234567"),
    ("Lund IT-Partner AB", "556345678"),
    ("Östra Hamnen Logistik AB", "556456789"),
    ("Björkdal Bygg & Montage AB", "556567891"),
    ("Grönvik Redovisning AB", "556678912"),
    ("Klarsyn Tryckeri AB", "556789123"),
    ("Vindkraft Syd AB", "556891234"),
]
SUPPLIERS = [(name, f"{base[:6]}-{base[6:]}{luhn_check_digit(base)}") for name, base in SUPPLIER_BASES]

ITEMS = [
    ("Konsulttimmar", 950), ("Kontorsstol", 2490), ("Skrivbord", 3990), ("Projektorlampa", 1290),
    ("Tryckning broschyr", 780), ("Serverunderhåll", 4200), ("Programvarulicens", 1850),
    ("Fraktavgift", 250), ("Whiteboardtavla", 1590), ("Utbildningsdag", 7500),
]

MONTHS_SV = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti",
             "september", "oktober", "november", "december"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_sv(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def fmt_en(value: Decimal) -> str:
    return f"{value:,.2f}"


def make_invoice(rng: random.Random, index: int, today: date) -> dict:
    name, org = rng.choice(SUPPLIERS)
    invoice_date = today - timedelta(days=rng.randint(5, 250))
    due_date = invoice_date + timedelta(days=rng.choice([10, 20, 30]))
    vat_rate = rng.choices([Decimal("0.25"), Decimal("0.12"), Decimal("0.06")], weights=[8, 1, 1])[0]

    lines = []
    for _ in range(rng.randint(1, 5)):
        description, price = rng.choice(ITEMS)
        quantity = Decimal(rng.randint(1, 8))
        unit_price = money(Decimal(price) * Decimal(str(rng.uniform(0.9, 1.1))))
        lines.append({
            "description": description,
            "quantity": str(quantity),
            "unit_price": str(unit_price),
            "line_total": str(money(quantity * unit_price)),
        })

    total_excl = sum((Decimal(line["line_total"]) for line in lines), Decimal("0"))
    vat = money(total_excl * vat_rate)
    return {
        "supplier_name": name,
        "supplier_org_number": org,
        "invoice_number": f"{invoice_date.year}-{rng.randint(1000, 9999)}-{index:03d}",
        "invoice_date": invoice_date.isoformat(),
        "due_date": due_date.isoformat(),
        "currency": "SEK",
        "lines": lines,
        "total_excl_vat": str(total_excl),
        "vat_amount": str(vat),
        "total_incl_vat": str(total_excl + vat),
        "expected_issues": [],
    }


def inject_flaw(rng: random.Random, data: dict) -> None:
    """Break one thing on purpose. The wrong value is what gets printed in the PDF."""
    flaw = rng.choice(["total_mismatch", "line_total_mismatch", "vat_rate_unusual"])
    if flaw == "total_mismatch":
        data["total_incl_vat"] = str(Decimal(data["total_incl_vat"]) + Decimal("100.00"))
        data["expected_issues"] = ["total_mismatch"]
    elif flaw == "line_total_mismatch":
        data["lines"][0]["line_total"] = str(Decimal(data["lines"][0]["line_total"]) + Decimal("10.00"))
        data["expected_issues"] = ["line_total_mismatch", "lines_sum_mismatch"]
    else:
        excl = Decimal(data["total_excl_vat"])
        vat = money(excl * Decimal("0.20"))
        data["vat_amount"] = str(vat)
        data["total_incl_vat"] = str(excl + vat)
        data["expected_issues"] = ["vat_rate_unusual"]


def render_lines(data: dict, layout: int) -> list[str]:
    d_iso, d_due = date.fromisoformat(data["invoice_date"]), date.fromisoformat(data["due_date"])
    lines = data["lines"]

    if layout == 0:  # Swedish, ISO dates
        out = ["FAKTURA", data["supplier_name"], f"Org.nr: {data['supplier_org_number']}", "",
               f"Fakturanummer: {data['invoice_number']}", f"Fakturadatum: {d_iso.isoformat()}",
               f"Förfallodatum: {d_due.isoformat()}", "Valuta: SEK", "",
               "Beskrivning        Antal   À-pris   Summa"]
        for line in lines:
            out.append(f"{line['description']}   {line['quantity']}   "
                       f"{fmt_sv(Decimal(line['unit_price']))}   {fmt_sv(Decimal(line['line_total']))}")
        out += ["", f"Summa exkl. moms: {fmt_sv(Decimal(data['total_excl_vat']))}",
                f"Moms: {fmt_sv(Decimal(data['vat_amount']))}",
                f"Att betala: {fmt_sv(Decimal(data['total_incl_vat']))} kr"]
        return out

    if layout == 1:  # English, month names, 1,234.50 style
        def long_date(value: date) -> str:
            return f"{value.day} {MONTHS_EN[value.month - 1]} {value.year}"
        out = ["INVOICE", data["supplier_name"], f"Company reg. no. {data['supplier_org_number']}", "",
               f"Invoice No: {data['invoice_number']}", f"Date: {long_date(d_iso)}",
               f"Due date: {long_date(d_due)}", "Currency: SEK", "",
               "Description    Qty    Unit price    Amount"]
        for line in lines:
            out.append(f"{line['description']}   {line['quantity']}   "
                       f"{fmt_en(Decimal(line['unit_price']))}   {fmt_en(Decimal(line['line_total']))}")
        out += ["", f"Subtotal: {fmt_en(Decimal(data['total_excl_vat']))}",
                f"VAT: {fmt_en(Decimal(data['vat_amount']))}",
                f"Total due: {fmt_en(Decimal(data['total_incl_vat']))} SEK"]
        return out

    # layout 2: messy Swedish, day-first slash dates, capital supplier name
    out = [data["supplier_name"].upper(), f"Organisationsnummer {data['supplier_org_number']}", "",
           f"FAKTURA NR {data['invoice_number']}", f"Datum {d_iso.day:02d}/{d_iso.month:02d}/{d_iso.year}",
           f"Förfaller {d_due.day} {MONTHS_SV[d_due.month - 1]} {d_due.year}", "Belopp i kronor (SEK)", ""]
    for line in lines:
        out.append(f"{line['quantity']} st {line['description']} a {fmt_sv(Decimal(line['unit_price']))} kr"
                   f" = {fmt_sv(Decimal(line['line_total']))} kr")
    out += ["", f"Netto {fmt_sv(Decimal(data['total_excl_vat']))} kr",
            f"Moms {fmt_sv(Decimal(data['vat_amount']))} kr",
            f"TOTALT {fmt_sv(Decimal(data['total_incl_vat']))} kr"]
    return out


def write_pdf(path: Path, text_lines: list[str]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for text in text_lines:
        pdf.setFont("Helvetica", 11)
        pdf.drawString(50, y, text)
        y -= 17
    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data")
    parser.add_argument("--flaw-rate", type=float, default=0.15)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pdf_dir, truth_dir = Path(args.out) / "invoices", Path(args.out) / "truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    flawed = 0
    for index in range(1, args.count + 1):
        data = make_invoice(rng, index, today)
        if rng.random() < args.flaw_rate:
            inject_flaw(rng, data)
            flawed += 1
        name = f"INV-{index:04d}"
        write_pdf(pdf_dir / f"{name}.pdf", render_lines(data, layout=rng.randint(0, 2)))
        (truth_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Made {args.count} invoices in {pdf_dir} ({flawed} with a deliberate flaw)")


if __name__ == "__main__":
    main()
