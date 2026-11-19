import subprocess
import sys

from eval.evaluate import evaluate
from eval.oracle import OracleClient


def test_oracle_gets_perfect_scores(tmp_path):
    subprocess.run([sys.executable, "-m", "generator.make_invoices", "--count", "20", "--seed", "3",
                    "--out", str(tmp_path), "--flaw-rate", "0.3"], check=True, capture_output=True)
    client = OracleClient(str(tmp_path / "truth"))
    report = evaluate(str(tmp_path / "invoices"), str(tmp_path / "truth"), client)
    summary = report["summary"]
    assert summary["field_accuracy_percent"] == 100.0
    assert summary["flaws_caught"] == summary["flawed_invoices"] > 0
    assert summary["clean_wrongly_flagged"] == 0
