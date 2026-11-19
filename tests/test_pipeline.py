"""Pipeline tests with a FakeClient: no internet, no cost."""
import json
from datetime import date

from agent.extractor import parse_json
from agent.llm import FakeClient
from pipeline import process_text
from tests.helpers import good_raw

TODAY = date(2026, 11, 19)
TEXT = "pretend this is the invoice text"


def answer(raw) -> str:
    return json.dumps(raw)


def test_valid_on_first_try():
    client = FakeClient([answer(good_raw())])
    result = process_text(TEXT, client, today=TODAY)
    assert result.status == "valid"
    assert result.attempts == 1
    assert len(client.calls) == 1


def test_repaired_on_second_try():
    wrong = good_raw(total_incl_vat="12 287,50")
    client = FakeClient([answer(wrong), answer(good_raw())])
    result = process_text(TEXT, client, today=TODAY)
    assert result.status == "repaired"
    assert result.attempts == 2
    # The repair call must contain the problem so the model can see it
    assert "total_mismatch" in client.calls[1][1]


def test_needs_review_after_max_retries():
    wrong = answer(good_raw(total_incl_vat="12 287,50"))
    client = FakeClient([wrong, wrong, wrong])
    result = process_text(TEXT, client, max_retries=2, today=TODAY)
    assert result.status == "needs_review"
    assert result.attempts == 3
    assert result.invoice is not None            # still readable, only the rule failed
    assert {issue.code for issue in result.issues} == {"total_mismatch"}


def test_invalid_json_is_repaired():
    client = FakeClient(["sorry, I cannot do that", answer(good_raw())])
    result = process_text(TEXT, client, today=TODAY)
    assert result.status == "repaired"


def test_duplicate_is_not_retried():
    seen = set()
    first = process_text(TEXT, FakeClient([answer(good_raw())]), today=TODAY, seen=seen)
    assert first.status == "valid"
    client = FakeClient([answer(good_raw())])
    second = process_text(TEXT, client, today=TODAY, seen=seen)
    assert second.status == "needs_review"
    assert len(client.calls) == 1                 # no wasted retries


def test_parse_json_is_forgiving():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here you go: {"a": 1} Thanks') == {"a": 1}
