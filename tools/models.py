"""Data shapes used everywhere in the project."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


@dataclass
class Issue:
    """One problem found in an extracted invoice."""

    code: str
    message: str
    field: Optional[str] = None
    retryable: bool = True  # False = asking the LLM again will not help

    def to_dict(self) -> dict:
        return asdict(self)


class LineItem(BaseModel):
    description: str = Field(min_length=1)
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class Invoice(BaseModel):
    supplier_name: str = Field(min_length=1)
    supplier_org_number: Optional[str] = None
    invoice_number: str = Field(min_length=1)
    invoice_date: date
    due_date: Optional[date] = None
    currency: str = Field(min_length=3, max_length=3)
    lines: list[LineItem] = Field(min_length=1)
    total_excl_vat: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
