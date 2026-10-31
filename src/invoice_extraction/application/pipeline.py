"""The pipeline use case: PDF in, validated Extraction or terminal status out.

A LangGraph graph (no checkpointer; state lives in DynamoDB) wires the stages:

    pre -> call -> post -> validate -> done
            ^ |            |
            | +-fall_back  +-- repair (back to call) / escalate (back to call)

`call` retries transient errors with jittered backoff. When a model is exhausted the
graph falls back from primary to fallback; if the fallback is exhausted too, the job
raises ModelUnavailableError so the queue can retry later. A validation failure is
repaired up to `max_repairs` times, then escalated once to the quality model.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from invoice_extraction.application.ports import (
    Example,
    ExtractionModel,
    ExtractionRequest,
    ModelRejectedError,
    ModelUnavailableError,
    Repair,
    TransientModelError,
)
from invoice_extraction.application.post_slot import PostSlot
from invoice_extraction.application.pre_slot import Prepared, PreSlot, RejectedError
from invoice_extraction.application.prompt_bundle import ModelSetting, PromptBundle
from invoice_extraction.domain.schema import Extraction, model_schema
from invoice_extraction.domain.status import JobStatus, TerminalReason


@dataclass(frozen=True)
class PipelineResult:
    status: JobStatus
    extraction: Extraction | None = None
    errors: list[str] = field(default_factory=list)
    reason: TerminalReason | None = None
    prompt_version: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class RetryPolicy:
    """Short in-process retries for transient 429/503; SQS handles long outages."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0


class _State(TypedDict, total=False):
    pdf: bytes
    prepared: Prepared
    tier: str  # primary | fallback | escalation
    escalated: bool
    repairs_used: int
    repair: Repair | None
    raw: dict[str, Any]  # as the model returned it: Placeholders intact
    restored: dict[str, Any]  # after Restore: real identifiers, never sent to the model
    call_ok: bool
    model: str
    errors: list[str]
    result: PipelineResult


class ExtractInvoice:
    def __init__(
        self,
        pre: PreSlot,
        model: ExtractionModel,
        post: PostSlot,
        bundle: PromptBundle,
        *,
        retry: RetryPolicy | None = None,
        max_repairs: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._pre = pre
        self._model = model
        self._post = post
        self._bundle = bundle
        self._retry = retry or RetryPolicy()
        self._max_repairs = max_repairs
        self._sleep = sleep
        self._rng = rng
        self._schema = model_schema()
        self.graph = self._build_graph()

    def __call__(self, pdf: bytes) -> PipelineResult:
        state = self.graph.invoke({"pdf": pdf, "tier": "primary", "repairs_used": 0})
        return replace(state["result"], prompt_version=self._bundle.version)

    # --- graph ---------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(_State)
        graph.add_node("pre", self._pre_node)
        graph.add_node("call", self._call_node)
        graph.add_node("fall_back", lambda state: {"tier": "fallback"})
        graph.add_node("post", self._post_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("repair", self._repair_node)
        graph.add_node("escalate", self._escalate_node)
        graph.add_node("give_up", lambda state: {"result": self._schema_invalid(state)})
        graph.add_node("unavailable", self._unavailable_node)
        graph.add_edge(START, "pre")
        graph.add_conditional_edges("pre", self._after_pre, ["call", END])
        graph.add_conditional_edges(
            "call", self._after_call, ["post", "fall_back", "unavailable", END]
        )
        graph.add_edge("fall_back", "call")
        graph.add_conditional_edges("post", self._after_post, ["validate", END])
        graph.add_conditional_edges(
            "validate", self._after_validate, ["repair", "escalate", "give_up", END]
        )
        graph.add_edge("repair", "call")
        graph.add_edge("escalate", "call")
        graph.add_edge("give_up", END)
        graph.add_edge("unavailable", END)
        return graph.compile()

    def _setting(self, tier: str) -> ModelSetting:
        return getattr(self._bundle, tier)

    def _pre_node(self, state: _State) -> _State:
        try:
            return {"prepared": self._pre(state["pdf"])}
        except RejectedError as rejected:
            return {
                "result": PipelineResult(
                    JobStatus.FAILED, errors=[str(rejected)], reason=rejected.reason
                )
            }

    @staticmethod
    def _after_pre(state: _State) -> str:
        return END if "result" in state else "call"

    def _call_node(self, state: _State) -> _State:
        setting = self._setting(state["tier"])
        request = ExtractionRequest(
            model=setting.name,
            text=state["prepared"].text,
            schema=self._schema,
            system_prompt=self._bundle.system_prompt,
            examples=tuple(Example(e.text, e.extraction) for e in self._bundle.examples),
            temperature=setting.temperature,
            repair=state.get("repair"),
        )
        for attempt in range(self._retry.max_attempts):
            try:
                raw = self._model.extract(request)
            except ModelRejectedError:
                break
            except TransientModelError:
                if attempt + 1 < self._retry.max_attempts:
                    self._sleep(self._backoff(attempt))
            else:
                return {"raw": raw, "call_ok": True, "model": setting.name}
        if state["tier"] == "escalation":
            # the quality model is a bonus: its outage ends the job as a validation failure
            return {"call_ok": False, "result": self._schema_invalid(state)}
        return {"call_ok": False}

    @staticmethod
    def _schema_invalid(state: _State) -> PipelineResult:
        return PipelineResult(
            JobStatus.FAILED_VALIDATION,
            errors=state.get("errors", []),
            reason=TerminalReason.SCHEMA_INVALID,
            model=state.get("model"),
        )

    def _backoff(self, attempt: int) -> float:
        cap = min(self._retry.max_delay, self._retry.base_delay * 2**attempt)
        return self._rng() * cap  # full jitter

    @staticmethod
    def _after_call(state: _State) -> str:
        if state["call_ok"]:
            return "post"
        if state["tier"] == "primary":
            return "fall_back"
        if state["tier"] == "fallback":
            return "unavailable"
        return END  # quality model unavailable: the node already set the result

    def _post_node(self, state: _State) -> _State:
        try:
            restored = self._post(state["raw"], state["prepared"].placeholders)
            return {"restored": restored}
        except RejectedError as rejected:
            return {
                "result": PipelineResult(
                    JobStatus.FAILED_VALIDATION,
                    errors=[str(rejected)],
                    reason=rejected.reason,
                    model=state["model"],
                )
            }

    @staticmethod
    def _after_post(state: _State) -> str:
        return END if "result" in state else "validate"

    def _validate_node(self, state: _State) -> _State:
        try:
            extraction = Extraction.model_validate(state["restored"])
        except ValidationError as error:
            messages = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
            return {"errors": messages}
        return {
            "result": PipelineResult(
                JobStatus.SUCCEEDED, extraction=extraction, model=state["model"]
            )
        }

    def _after_validate(self, state: _State) -> str:
        if "result" in state:
            return END
        if state["repairs_used"] < self._max_repairs:
            return "repair"
        if not state.get("escalated"):
            return "escalate"
        return "give_up"

    def _repair_node(self, state: _State) -> _State:
        repair = Repair(
            instruction=self._bundle.repair_prompt,
            previous=state["raw"],
            errors=tuple(state["errors"]),
        )
        return {"repair": repair, "repairs_used": state["repairs_used"] + 1}

    @staticmethod
    def _escalate_node(state: _State) -> _State:
        return {"tier": "escalation", "escalated": True, "repairs_used": 0, "repair": None}

    @staticmethod
    def _unavailable_node(state: _State) -> _State:
        raise ModelUnavailableError("primary and fallback models are unavailable")
