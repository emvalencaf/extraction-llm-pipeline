"""Train-Set-shaped sample data: raw strings as the model returns them."""

from support.pdf import make_pdf

INVOICE_LINES = [
    "Invoice no: 51109301",
    "Date of issue: 03/07/2023",
    "Seller: TechVision Distributors Pvt Ltd",
    "Client: Jane Roe",
    "1. Widget 9.00 pcs 74,120.00 667,080.00 10% 733,788.00",
]


# Mirrors the dataset template: two columns (Seller | Client) flattened line by line.
TWO_COLUMN_TEXT = """Invoice no: 51109301
Date of issue: 03/07/2023
Seller: Client:
TechVision Distributors Pvt Ltd Raj Electronics Pvt Ltd
Plot 14, MIDC Industrial Area, Andheri East 42 MG Road
Mumbai, Maharashtra - 400093 Bengaluru, Karnataka - 560001
Tax Id: 27AABCT1234F1Z5 Tax Id: 901-95-4704
GSTIN: 27AABCT1234F1Z5
ITEMS
1. Garmin Fenix 7 Solar Multisport GPS 9.00 pcs 74,120.00 667,080.00 10% 733,788.00
SUMMARY
10% 1,676,976.00 167,697.60 1,844,673.60
Total INR 1,676,976.00 INR 1,844,673.60"""

# Ground Truth sensitive values; an address is leaked if any of its parts survives.
SENSITIVE_VALUES = [
    "TechVision Distributors Pvt Ltd",
    "Raj Electronics Pvt Ltd",
    "Plot 14, MIDC Industrial Area, Andheri East",
    "Mumbai, Maharashtra - 400093",
    "42 MG Road",
    "Bengaluru, Karnataka - 560001",
    "27AABCT1234F1Z5",
    "901-95-4704",
]

# Same shape, with the contact and bank details the dataset lacks.
CONTACT_TEXT = """Invoice no: 7001
Seller: Client:
Acme Traders Pvt Ltd Beta Foods Private Limited
12 Park Street 7 Lake Road
Kolkata, West Bengal - 700016 Pune, Maharashtra - 411001
Tax Id: 19AAACA1234B1Z9 Tax Id: 123-45-6789
Email: accounts@acmetraders.in
Phone: +91 98765 43210
Bank A/C No: 123456789012 IFSC: HDFC0001234"""

CONTACT_VALUES = [
    "Acme Traders Pvt Ltd",
    "Beta Foods Private Limited",
    "19AAACA1234B1Z9",
    "123-45-6789",
    "accounts@acmetraders.in",
    "98765 43210",
    "123456789012",
    "HDFC0001234",
    "12 Park Street",
    "7 Lake Road",
    "Kolkata, West Bengal - 700016",
    "Pune, Maharashtra - 411001",
]


def leak_rate(texts_and_values: list[tuple[str, list[str]]]) -> float:
    """Share of invoices where any Ground Truth sensitive value still appears in the text."""
    leaked = sum(any(v in text for v in values) for text, values in texts_and_values)
    return leaked / len(texts_and_values)


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
