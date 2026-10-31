"""HTTP `fake-gemini` for the container stack: the in-process FakeGemini behind a socket.

`POST /extract` {text, schema} returns the current canned reply. `PUT /control/reply`
replaces it (the control endpoint tests use to steer the stack); `DELETE /control/reply`
restores the default. `PUT /control/fail` {status} makes every /extract answer that HTTP
error (e.g. 503) until `DELETE /control/fail`.

Failure injection: `POST /control/scenario` adds a rule, `DELETE /control/scenario` removes
all rules and the call log, `GET /control/calls` lists the calls seen as {model, outcome}.
A rule is {mode, model?, times?}: `model` limits it to one model name, `times` to that many
calls (every call when absent). Rules are tried in the order added; the first live match
wins. Modes: `error` {status} answers that HTTP error, `reply` {reply?, patch?} answers a
replacement reply or the default with `patch` deep-merged in, `crash` {hang_seconds} holds
the call open (past the Lambda timeout, to simulate a worker that dies) then answers 504.
"""

import copy
import threading
import time
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


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def create_app() -> FastAPI:
    app = FastAPI(title="fake-gemini")
    reply: dict[str, Any] = copy.deepcopy(DEFAULT_REPLY)
    failing: dict[str, int] = {}
    scenarios: list[dict[str, Any]] = []
    calls: list[dict[str, str]] = []
    lock = threading.Lock()
    model = FakeGemini(reply=lambda _text: reply)

    def take_scenario(model_name: str) -> dict[str, Any] | None:
        """The first live rule matching this model, with one of its calls consumed."""
        with lock:
            for rule in scenarios:
                if rule.get("model") not in (None, model_name):
                    continue
                if rule.get("times") is not None:
                    if rule["times"] <= 0:
                        continue
                    rule["times"] -= 1
                return rule
        return None

    def log_call(model_name: str, outcome: str) -> None:
        with lock:
            calls.append({"model": model_name, "outcome": outcome})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/extract")
    def extract(payload: dict[str, Any]) -> dict[str, Any]:
        model_name = payload.get("model", "fake")
        if failing:
            log_call(model_name, f"error:{failing['status']}")
            raise HTTPException(status_code=failing["status"], detail="injected failure")
        rule = take_scenario(model_name)
        if rule is not None and rule["mode"] == "error":
            log_call(model_name, f"error:{rule['status']}")
            raise HTTPException(status_code=rule["status"], detail="injected failure")
        if rule is not None and rule["mode"] == "crash":
            log_call(model_name, "crash")
            time.sleep(rule.get("hang_seconds", 30))
            raise HTTPException(status_code=504, detail="injected crash")
        log_call(model_name, "ok")
        if rule is not None and rule["mode"] == "reply":
            if "reply" in rule:
                return rule["reply"]
            return _merge(reply, rule.get("patch", {}))
        return model.extract(
            ExtractionRequest(
                model=model_name,
                text=payload["text"],
                schema=payload["schema"],
                system_prompt="",
            )
        ).data

    @app.post("/control/scenario")
    def add_scenario(rule: dict[str, Any]) -> dict[str, str]:
        with lock:
            scenarios.append(rule)
        return {"status": "ok"}

    @app.delete("/control/scenario")
    def clear_scenarios() -> dict[str, str]:
        with lock:
            scenarios.clear()
            calls.clear()
        return {"status": "ok"}

    @app.get("/control/calls")
    def list_calls() -> list[dict[str, str]]:
        with lock:
            return list(calls)

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
