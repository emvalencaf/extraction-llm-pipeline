"""Grounding Rate: how many extracted values can be found in the document text.

Informational only; it never blocks a job. It covers non-anonymized fields (invoice
number, date, currency, line items, totals). Seller and client fields are Placeholders
in the text the model saw, so they cannot be checked and are left out.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from invoice_extraction.domain.schema import parse_amount, parse_date

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_AMOUNT_FIELDS = {"quantity", "unit_price", "net_amount", "vat_pct", "gross_amount", "vat_amount"}
_ANONYMIZED = ("seller", "client")


@dataclass(frozen=True)
class GroundingRate:
    grounded: int
    total: int
    ungrounded: tuple[str, ...] = ()  # field paths, never values

    @property
    def rate(self) -> float:
        return self.grounded / self.total if self.total else 1.0


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


def _leaves(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            if not path and key in _ANONYMIZED:
                continue
            yield from _leaves(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path, value


def _numbers(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for token in _NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except ArithmeticError:
            continue
    return found


def _is_grounded(path: str, value: Any, text: str, numbers: set[Decimal]) -> bool:
    raw = str(value)
    if _fold(raw) and _fold(raw) in text:
        return True
    name = re.sub(r"\[\d+\]", "", path).rsplit(".", 1)[-1]
    try:
        if name in _AMOUNT_FIELDS:
            return parse_amount(raw) in numbers
        if name == "issue_date":
            day = parse_date(raw)
            return day.isoformat() in text or day.strftime("%d/%m/%Y") in text
    except (ValueError, ArithmeticError):
        return False
    return False


def grounding_rate(raw: dict[str, Any], document_text: str) -> GroundingRate:
    """Check each non-anonymized value of the (restored) raw extraction against the text."""
    text = _fold(document_text)
    numbers = _numbers(document_text)
    ungrounded: list[str] = []
    total = 0
    for path, value in _leaves(raw):
        total += 1
        if not _is_grounded(path, value, text, numbers):
            ungrounded.append(path)
    return GroundingRate(total - len(ungrounded), total, tuple(ungrounded))
