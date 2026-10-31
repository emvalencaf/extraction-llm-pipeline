"""Train-Set-shaped sample data: raw strings as the model returns them."""

from support.pdf import make_pdf

INVOICE_LINES = [
    "Invoice no: 51109301",
    "Date of issue: 03/07/2023",
    "Seller: TechVision Distributors Pvt Ltd",
    "Client: Jane Roe",
    "1. Widget 9.00 pcs 74,120.00 667,080.00 10% 733,788.00",
]


def invoice_pdf() -> bytes:
    return make_pdf(INVOICE_LINES)


def raw_extraction() -> dict:
    """What the model returns: every value a string, source formats intact."""
    return {
        "invoice_no": "51109301",
        "issue_date": "03/07/2023",
        "currency": "INR",
        "seller": {
            "name": "TechVision Distributors Pvt Ltd",
            "address": "1 Main Street, Mumbai",
            "tax_id": "27AAAAA0000A1Z5",
        },
        "client": {
            "name": "Jane Roe",
            "address": "2 Side Road, Delhi",
            "tax_id": "901-95-4704",
        },
        "items": [
            {
                "description": "Widget",
                "quantity": "9.00",
                "unit": "pcs",
                "unit_price": "74,120.00",
                "net_amount": "667,080.00",
                "vat_pct": "10%",
                "gross_amount": "733,788.00",
            }
        ],
        "totals": {
            "vat_pct": "10%",
            "net_amount": "667,080.00",
            "vat_amount": "66,708.00",
            "gross_amount": "733,788.00",
        },
    }
