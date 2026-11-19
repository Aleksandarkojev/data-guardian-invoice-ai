"""A pretend 'LLM' that already knows the right answers. Free, instant, always correct.

Use it to test the plumbing and to see the best possible score:
    python -m eval.evaluate --provider oracle
"""
import json
from pathlib import Path


class OracleClient:
    def __init__(self, truth_dir: str):
        self.truths = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(truth_dir).glob("*.json"))]
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        for truth in self.truths:
            if truth["invoice_number"] in user:
                answer = {key: value for key, value in truth.items() if key != "expected_issues"}
                return json.dumps(answer, ensure_ascii=False)
        return "{}"
