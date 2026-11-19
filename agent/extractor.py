"""LLM part: text -> raw JSON, and a repair step that uses the validation errors.

Important rule in both prompts: copy what the document says, do NOT calculate or fix numbers.
Fixing numbers is the job of validation (and a human), not of the model.
"""
from __future__ import annotations

import json
import re

from tools.models import Issue

SYSTEM_PROMPT = """You extract data from invoice text and return ONLY one JSON object (no markdown, no explanation).

Use exactly these keys:
{
  "supplier_name": string,
  "supplier_org_number": string or null,
  "invoice_number": string,
  "invoice_date": string,
  "due_date": string or null,
  "currency": string,
  "lines": [ {"description": string, "quantity": string, "unit_price": string, "line_total": string} ],
  "total_excl_vat": string,
  "vat_amount": string,
  "total_incl_vat": string
}

Rules:
- Copy values exactly as written in the document. Keep dates and amounts as written.
- Do NOT calculate, correct or guess numbers. If the document has a wrong number, copy the wrong number.
- Use null when a value is not in the document.
- One object in "lines" for each invoice row."""

REPAIR_PROMPT = """Below are an invoice text, your earlier JSON, and problems found by automatic checks.

Read the invoice text again. Fix only real reading mistakes (wrong row, missed digit, wrong field).
If the invoice text itself shows these values, keep them exactly. Do NOT recalculate or invent numbers.
Return ONLY the corrected JSON object, using the same keys as before."""


class ExtractionError(Exception):
    pass


def parse_json(text: str) -> dict:
    """Be forgiving: remove code fences and text around the JSON object."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError("The model did not return a JSON object")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("JSON is not an object")
    return data


def extract(client, text: str) -> dict:
    answer = client.complete(SYSTEM_PROMPT, f"Invoice text:\n\n{text}")
    return parse_json(answer)


def repair(client, text: str, previous_raw: dict, issues: list[Issue]) -> dict:
    problems = "\n".join(f"- {issue.code}: {issue.message}" for issue in issues)
    user = (
        f"Invoice text:\n\n{text}\n\n"
        f"Your earlier JSON:\n{json.dumps(previous_raw, ensure_ascii=False, indent=2)}\n\n"
        f"Problems found:\n{problems}"
    )
    answer = client.complete(SYSTEM_PROMPT + "\n\n" + REPAIR_PROMPT, user)
    return parse_json(answer)
