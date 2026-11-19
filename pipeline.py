"""The whole flow: PDF -> text -> LLM extract -> clean -> validate -> (repair loop) -> MySQL.

Run it:  python -m pipeline data/invoices --limit 3
         python -m pipeline data/invoices --save-db
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from agent.extractor import ExtractionError, extract, repair
from tools.models import Invoice, Issue
from tools.pdf_text import pdf_to_text
from tools.validation import build_invoice


@dataclass
class Result:
    source_file: str
    status: str  # "valid" | "repaired" | "needs_review"
    invoice: Optional[Invoice]
    issues: list[Issue] = field(default_factory=list)
    attempts: int = 1
    raw: Optional[dict] = None


def process_text(
    text: str,
    client,
    source_file: str = "",
    max_retries: int = 2,
    today: Optional[date] = None,
    seen: Optional[set] = None,
) -> Result:
    """Extract, validate and (if needed) repair one invoice text."""
    raw: Optional[dict] = None
    invoice: Optional[Invoice] = None
    issues: list[Issue] = []

    try:
        raw = extract(client, text)
    except ExtractionError as exc:
        issues = [Issue("invalid_json", str(exc))]

    attempt = 1
    while True:
        if raw is not None:
            invoice, issues = build_invoice(raw, today=today, seen=seen)
        if not issues:
            if seen is not None and invoice is not None:
                seen.add((invoice.supplier_name, invoice.invoice_number))
            return Result(source_file, "valid" if attempt == 1 else "repaired", invoice, [], attempt, raw)

        can_retry = attempt <= max_retries and any(issue.retryable for issue in issues)
        if not can_retry:
            return Result(source_file, "needs_review", invoice, issues, attempt, raw)

        attempt += 1
        try:
            raw = repair(client, text, raw or {}, issues)
        except ExtractionError as exc:
            raw = None
            issues = [Issue("invalid_json", str(exc))]


def process_pdf(path, client, **kwargs) -> Result:
    return process_text(pdf_to_text(path), client, source_file=Path(str(path)).name, **kwargs)


def run_folder(folder: str, client, limit: Optional[int] = None, conn=None, max_retries: int = 2) -> list[Result]:
    files = sorted(Path(folder).glob("*.pdf"))
    if limit:
        files = files[:limit]

    seen: set = set()
    results: list[Result] = []
    for path in files:
        result = process_pdf(path, client, seen=seen, max_retries=max_retries)
        if conn is not None:
            from tools.loader import DuplicateInvoice, load_invoice, save_for_review

            if result.status in ("valid", "repaired") and result.invoice is not None:
                try:
                    load_invoice(conn, result.invoice, source_file=result.source_file)
                except DuplicateInvoice:
                    result.status = "needs_review"
                    result.issues.append(Issue("duplicate_invoice", "Already in the database", retryable=False))
                    save_for_review(conn, result.source_file, result.raw, result.issues)
            else:
                save_for_review(conn, result.source_file, result.raw, result.issues)
        results.append(result)
        print(f"{result.source_file}: {result.status} (attempts: {result.attempts})")
        for issue in result.issues:
            print(f"    - {issue.code}: {issue.message}")
    return results


def main() -> None:
    from agent.llm import get_client

    parser = argparse.ArgumentParser(description="Turn invoice PDFs into structured data")
    parser.add_argument("folder", help="Folder with PDF invoices, for example data/invoices")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N files")
    parser.add_argument("--save-db", action="store_true", help="Save results to MySQL")
    args = parser.parse_args()

    conn = None
    if args.save_db:
        from tools.loader import get_connection

        conn = get_connection()
    results = run_folder(args.folder, get_client(), limit=args.limit, conn=conn)

    counts = {status: sum(1 for r in results if r.status == status) for status in ("valid", "repaired", "needs_review")}
    print(f"\nDone: {counts}")


if __name__ == "__main__":
    main()
