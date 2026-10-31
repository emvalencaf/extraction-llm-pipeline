"""The Extraction Schema: single definition of an Extraction.

The model-facing schema (`model_schema`) and the client-side validation both derive
from the classes below. The model returns strings in the source formats; Normalization
to Decimal and ISO dates happens here, in code, outside the model call.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, WithJsonSchema

_DAY_FIRST = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_amount(value: Any) -> Decimal:
    """Normalize "INR 1,676,976.00", "74,120.00" or "10%" to a Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError(f"amount must be a string, got {type(value).__name__}")
    cleaned = re.sub(r"[A-Za-z%\s]", "", value).replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not an amount: {value!r}") from None


def parse_date(value: Any) -> date:
    """Normalize an ISO date or a source dd/mm/yyyy date to a date."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"date must be a string, got {type(value).__name__}")
    text = value.strip()
    match = _DAY_FIRST.match(text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        return date(year, month, day)
    return date.fromisoformat(text)


Amount = Annotated[
    Decimal,
    BeforeValidator(parse_amount),
    WithJsonSchema({"type": "string", "description": "Amount exactly as printed"}),
]
IssueDate = Annotated[
    date,
    BeforeValidator(parse_date),
    WithJsonSchema({"type": "string", "description": "Date exactly as printed"}),
]


class _Strict(BaseModel):
    # one canonical value per fact: unknown (duplicate) fields are rejected
    model_config = ConfigDict(extra="forbid")


class Party(_Strict):
    name: str
    address: str
    tax_id: str


class LineItem(_Strict):
    description: str
    quantity: Amount
    unit: str
    unit_price: Amount
    net_amount: Amount
    vat_pct: Amount
    gross_amount: Amount


class Totals(_Strict):
    vat_pct: Amount
    net_amount: Amount
    vat_amount: Amount
    gross_amount: Amount


class Extraction(_Strict):
    invoice_no: str
    issue_date: IssueDate
    currency: str
    seller: Party
    client: Party
    items: list[LineItem]
    totals: Totals


def model_schema() -> dict[str, Any]:
    """JSON schema handed to the model, derived from the Extraction Schema."""
    return Extraction.model_json_schema(mode="validation")
