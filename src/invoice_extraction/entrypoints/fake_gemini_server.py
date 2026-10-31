"""HTTP `fake-gemini` for the container stack: the in-process FakeGemini behind a socket.

`POST /extract` {text, schema} returns the current canned reply. `PUT /control/reply`
replaces it (the control endpoint tests use to steer the stack); `DELETE /control/reply`
restores the default. `PUT /control/fail` {status} makes every /extract answer that HTTP
error (e.g. 503) until `DELETE /control/fail`.
"""

import copy
from typing import Any

from fastapi import FastAPI, HTTPException

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.application.ports import ExtractionRequest

DEFAULT_REPLY: dict[str, Any] = {
    "invoice_no": "51109301",
    "issue_date": "03/07/2023",
    "currency": "INR",
    "seller": {
        "name": "TechVision Distributors Pvt Ltd",
        "address": "1 Main Street, Mumbai",
        "tax_id": "27AAAAA0000A1Z5",
    },
    "client": {"name": "Jane Roe", "address": "2 Side Road, Delhi", "tax_id": "901-95-4704"},
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


def create_app() -> FastAPI:
    app = FastAPI(title="fake-gemini")
    reply: dict[str, Any] = copy.deepcopy(DEFAULT_REPLY)
    failing: dict[str, int] = {}
    model = FakeGemini(reply=lambda _text: reply)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/extract")
    def extract(payload: dict[str, Any]) -> dict[str, Any]:
        if failing:
            raise HTTPException(status_code=failing["status"], detail="injected failure")
        return model.extract(
            ExtractionRequest(
                model=payload.get("model", "fake"),
                text=payload["text"],
                schema=payload["schema"],
                system_prompt="",
            )
        ).data

    @app.put("/control/reply")
    def set_reply(new_reply: dict[str, Any]) -> dict[str, str]:
        reply.clear()
        reply.update(new_reply)
        return {"status": "ok"}

    @app.put("/control/fail")
    def set_failure(body: dict[str, int]) -> dict[str, str]:
        failing["status"] = body.get("status", 503)
        return {"status": "ok"}

    @app.delete("/control/fail")
    def clear_failure() -> dict[str, str]:
        failing.clear()
        return {"status": "ok"}

    @app.delete("/control/reply")
    def reset_reply() -> dict[str, str]:
        reply.clear()
        reply.update(copy.deepcopy(DEFAULT_REPLY))
        return {"status": "ok"}

    return app


app = create_app()
