"""Map a Kaggle ground-truth record to an Extraction Schema shaped dict.

The Kaggle labels use other names (net_price, net_worth, gross_worth, summary.*, gstin,
INR-prefixed duplicates). This pure function is the single place that translates them, so
few-shot examples and the regression gate score against the same shape. Values stay
strings in their source format; Normalization is done by the schema, not here.
"""

import re
from typing import Any

_CURRENCY = re.compile(r"^\s*([A-Z]{3})\b")


def _clean(value: Any) -> str:
    """Collapse stray newlines and repeated spaces (a known label defect)."""
    return re.sub(r"\s+", " ", str(value)).strip()


def _first(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if source.get(key) not in (None, ""):
            return _clean(source[key])
    raise KeyError(f"none of {keys} in ground-truth record")


def _party(party: dict[str, Any]) -> dict[str, str]:
    return {
        "name": _clean(party["name"]),
        "address": _clean(party["address"]),
        "tax_id": _first(party, "tax_id", "gstin"),
    }


def _currency(summary: dict[str, Any]) -> str:
    for key in ("total_net_worth", "total_vat", "total_gross_worth"):
        match = _CURRENCY.match(str(summary.get(key, "")))
        if match:
            return match.group(1)
    return "INR"


def ground_truth_to_extraction(record: dict[str, Any]) -> dict[str, Any]:
    summary = record["summary"]
    return {
        "invoice_no": _clean(record["invoice_no"]),
        "issue_date": _clean(record["date_of_issue"]),
        "currency": _currency(summary),
        "seller": _party(record["seller"]),
        "client": _party(record["client"]),
        "items": [
            {
                "description": _clean(item["description"]),
                "quantity": _clean(item["quantity"]),
                "unit": _clean(item["unit_measure"]),
                "unit_price": _clean(item["net_price"]),
                "net_amount": _clean(item["net_worth"]),
                "vat_pct": _clean(item["vat_pct"]),
                "gross_amount": _clean(item["gross_worth"]),
            }
            for item in record["items"]
        ],
        "totals": {
            "vat_pct": _clean(summary["vat_pct"]),
            "net_amount": _first(summary, "net_worth", "total_net_worth"),
            "vat_amount": _first(summary, "vat_amount", "total_vat"),
            "gross_amount": _first(summary, "gross_worth", "total_gross_worth"),
        },
    }
