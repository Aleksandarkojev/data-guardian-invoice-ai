"""The fake invoices and the validation rules must agree with each other."""
import json
import subprocess
import sys
from pathlib import Path

from tools.pdf_text import pdf_to_text
from tools.validation import build_invoice


def make(tmp_path: Path, count=30, seed=7):
    subprocess.run(
        [sys.executable, "-m", "generator.make_invoices", "--count", str(count), "--seed", str(seed),
         "--out", str(tmp_path), "--flaw-rate", "0.3"],
        check=True, capture_output=True,
    )


def test_pdfs_contain_invoice_numbers(tmp_path):
    make(tmp_path, count=5)
    for truth_file in sorted((tmp_path / "truth").glob("*.json")):
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        text = pdf_to_text(tmp_path / "invoices" / f"{truth_file.stem}.pdf")
        assert truth["invoice_number"] in text


def test_validation_finds_exactly_the_injected_flaws(tmp_path):
    make(tmp_path)
    flawed = 0
    for truth_file in sorted((tmp_path / "truth").glob("*.json")):
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        invoice, issues = build_invoice(truth)
        assert invoice is not None, truth_file.name
        assert {issue.code for issue in issues} == set(truth["expected_issues"]), truth_file.name
        flawed += bool(truth["expected_issues"])
    assert flawed > 0
