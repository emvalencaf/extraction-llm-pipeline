"""The Kaggle ground-truth record to Extraction Schema mapping (pure function)."""

import copy
import json
from pathlib import Path

from invoice_extraction.domain.ground_truth import ground_truth_to_extraction
from invoice_extraction.domain.schema import Extraction

FIXTURE = Path(__file__).parent / "fixtures" / "ground_truth_51109301.json"


def record() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_renames_kaggle_fields_to_schema_names():
    mapped = ground_truth_to_extraction(record())

    assert mapped["issue_date"] == "03/07/2023"
    assert mapped["items"][0] == {
        "description": "Garmin Fenix 7 Solar Multisport GPS",
        "quantity": "9.00",
        "unit": "pcs",
        "unit_price": "74,120.00",
        "net_amount": "667,080.00",
        "vat_pct": "10%",
        "gross_amount": "733,788.00",
    }
    assert mapped["totals"] == {
        "vat_pct": "10%",
        "net_amount": "1,676,976.00",
        "vat_amount": "167,697.60",
        "gross_amount": "1,844,673.60",
    }


def test_keeps_one_canonical_value_per_fact():
    mapped = ground_truth_to_extraction(record())

    assert mapped["seller"] == {
        "name": "TechVision Distributors Pvt Ltd",
        "address": "Plot 14, MIDC Industrial Area, Andheri East, Mumbai, Maharashtra - 400093",
        "tax_id": "27AABCT1234F1Z5",
    }
    assert mapped["currency"] == "INR"
    assert "item_no" not in mapped["items"][0]


def test_output_validates_against_the_extraction_schema():
    extraction = Extraction.model_validate(ground_truth_to_extraction(record()))

    assert str(extraction.totals.gross_amount) == "1844673.60"


def test_falls_back_to_gstin_and_inr_prefixed_totals():
    source = record()
    del source["seller"]["tax_id"]
    for key in ("net_worth", "vat_amount", "gross_worth"):
        del source["summary"][key]

    mapped = ground_truth_to_extraction(source)

    assert mapped["seller"]["tax_id"] == "27AABCT1234F1Z5"
    assert mapped["totals"]["net_amount"] == "INR 1,676,976.00"
    assert mapped["totals"]["gross_amount"] == "INR 1,844,673.60"


def test_stray_newlines_in_labels_are_collapsed():
    source = record()
    source["items"][1]["description"] = "Apple Watch Series 9 GPS 45mm\nMidnight "

    mapped = ground_truth_to_extraction(source)

    assert mapped["items"][1]["description"] == "Apple Watch Series 9 GPS 45mm Midnight"


def test_does_not_mutate_the_record():
    source = record()
    snapshot = copy.deepcopy(source)

    ground_truth_to_extraction(source)

    assert source == snapshot
