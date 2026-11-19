"""Measure how good the pipeline really is, using the fake invoices and their correct answers.

Run:  python -m eval.evaluate                      (uses LLM_PROVIDER from .env)
      python -m eval.evaluate --provider oracle    (free test with a perfect pretend model)
      python -m eval.evaluate --limit 10
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pipeline import process_pdf
from tools.models import Invoice

HEADER_FIELDS = ["supplier_name", "supplier_org_number", "invoice_number", "invoice_date",
                 "due_date", "currency", "total_excl_vat", "vat_amount", "total_incl_vat"]
DATE_FIELDS = {"invoice_date", "due_date"}
MONEY_FIELDS = {"total_excl_vat", "vat_amount", "total_incl_vat"}


def _same(field: str, actual, expected) -> bool:
    if actual is None or expected is None:
        return actual is None and expected is None
    if field in DATE_FIELDS:
        return actual.isoformat() == expected
    if field in MONEY_FIELDS or field in {"quantity", "unit_price", "line_total"}:
        return Decimal(str(actual)) == Decimal(str(expected))
    return str(actual).strip() == str(expected).strip()


def compare(invoice: Optional[Invoice], truth: dict) -> tuple[int, int]:
    """Return (correct fields, total fields) for one invoice."""
    total = len(HEADER_FIELDS) + 1 + 4 * len(truth["lines"])  # +1 for the number of lines
    if invoice is None:
        return 0, total

    correct = sum(_same(f, getattr(invoice, f), truth[f]) for f in HEADER_FIELDS)
    correct += len(invoice.lines) == len(truth["lines"])
    for actual, expected in zip(invoice.lines, truth["lines"]):
        for f in ("description", "quantity", "unit_price", "line_total"):
            correct += _same(f, getattr(actual, f), expected[f])
    return correct, total


def evaluate(folder: str, truth_dir: str, client, limit: Optional[int] = None) -> dict:
    files = sorted(Path(folder).glob("*.pdf"))[:limit]
    seen: set = set()
    rows = []
    for path in files:
        truth = json.loads((Path(truth_dir) / f"{path.stem}.json").read_text(encoding="utf-8"))
        result = process_pdf(path, client, seen=seen)
        correct, total = compare(result.invoice, truth)
        expected = set(truth["expected_issues"])
        found = {issue.code for issue in result.issues}
        rows.append({
            "file": path.name, "status": result.status, "attempts": result.attempts,
            "fields_correct": correct, "fields_total": total,
            "expected_issues": sorted(expected), "found_issues": sorted(found),
        })

    flawed = [r for r in rows if r["expected_issues"]]
    clean = [r for r in rows if not r["expected_issues"]]
    summary = {
        "invoices": len(rows),
        "valid_first_try": sum(r["status"] == "valid" for r in rows),
        "repaired": sum(r["status"] == "repaired" for r in rows),
        "needs_review": sum(r["status"] == "needs_review" for r in rows),
        "field_accuracy_percent": round(100 * sum(r["fields_correct"] for r in rows)
                                        / max(1, sum(r["fields_total"] for r in rows)), 1),
        "flawed_invoices": len(flawed),
        "flaws_caught": sum(r["status"] == "needs_review" and set(r["expected_issues"]) <= set(r["found_issues"])
                            for r in flawed),
        "clean_invoices": len(clean),
        "clean_wrongly_flagged": sum(r["status"] == "needs_review" for r in clean),
        "model_calls_per_invoice": round(sum(r["attempts"] for r in rows) / max(1, len(rows)), 2),
    }
    return {"summary": summary, "rows": rows}


def to_markdown(summary: dict) -> str:
    return "\n".join([
        "| Measure | Result |",
        "|---|---|",
        f"| Invoices tested | {summary['invoices']} |",
        f"| Valid on first try | {summary['valid_first_try']} |",
        f"| Fixed by retry | {summary['repaired']} |",
        f"| Sent to review | {summary['needs_review']} |",
        f"| Field accuracy | {summary['field_accuracy_percent']}% |",
        f"| Deliberate flaws caught | {summary['flaws_caught']} of {summary['flawed_invoices']} |",
        f"| Clean invoices wrongly flagged | {summary['clean_wrongly_flagged']} of {summary['clean_invoices']} |",
        f"| Model calls per invoice | {summary['model_calls_per_invoice']} |",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/invoices")
    parser.add_argument("--truth", default="data/truth")
    parser.add_argument("--provider", default=None, help="openai, anthropic or oracle")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.provider == "oracle":
        from eval.oracle import OracleClient
        client = OracleClient(args.truth)
    else:
        from agent.llm import get_client
        client = get_client(args.provider)

    report = evaluate(args.folder, args.truth, client, args.limit)
    Path("eval").mkdir(exist_ok=True)
    Path("eval/results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = to_markdown(report["summary"])
    Path("eval/results.md").write_text(markdown + "\n", encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
