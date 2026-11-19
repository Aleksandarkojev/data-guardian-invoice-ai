"""Save valid invoices to MySQL. Invoices that could not be fixed go to needs_review."""
from __future__ import annotations

import json
import os
from typing import Optional

import mysql.connector
from dotenv import load_dotenv

from tools.models import Invoice, Issue


class DuplicateInvoice(Exception):
    pass


def get_connection():
    load_dotenv()
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "invoice_ai"),
    )


def _get_or_create_supplier(cursor, name: str, org_number: Optional[str]) -> int:
    if org_number:
        cursor.execute("SELECT supplier_id FROM suppliers WHERE org_number = %s", (org_number,))
    else:
        cursor.execute("SELECT supplier_id FROM suppliers WHERE name = %s AND org_number IS NULL", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO suppliers (name, org_number) VALUES (%s, %s)", (name, org_number))
    return cursor.lastrowid


def load_invoice(conn, invoice: Invoice, source_file: Optional[str] = None) -> int:
    """Insert supplier, invoice and lines in ONE transaction. Returns the new invoice_id."""
    cursor = conn.cursor()
    try:
        supplier_id = _get_or_create_supplier(cursor, invoice.supplier_name, invoice.supplier_org_number)
        cursor.execute(
            """INSERT INTO invoices (supplier_id, invoice_number, invoice_date, due_date, currency,
                                     total_excl_vat, vat_amount, total_incl_vat, source_file)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (supplier_id, invoice.invoice_number, invoice.invoice_date, invoice.due_date, invoice.currency,
             invoice.total_excl_vat, invoice.vat_amount, invoice.total_incl_vat, source_file),
        )
        invoice_id = cursor.lastrowid
        cursor.executemany(
            """INSERT INTO invoice_lines (invoice_id, line_no, description, quantity, unit_price, line_total)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [(invoice_id, number, line.description, line.quantity, line.unit_price, line.line_total)
             for number, line in enumerate(invoice.lines, start=1)],
        )
        conn.commit()
        return invoice_id
    except mysql.connector.IntegrityError as exc:
        conn.rollback()
        if exc.errno == 1062:  # duplicate key
            raise DuplicateInvoice(f"{invoice.supplier_name} / {invoice.invoice_number}") from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def save_for_review(conn, source_file: str, raw: Optional[dict], issues: list[Issue]) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO needs_review (source_file, raw_json, issues) VALUES (%s, %s, %s)",
            (source_file, json.dumps(raw, default=str) if raw is not None else None,
             json.dumps([issue.to_dict() for issue in issues])),
        )
        conn.commit()
    finally:
        cursor.close()
