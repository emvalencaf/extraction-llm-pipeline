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

from invoice_extraction.application.grounding import GroundingRate, grounding_rate
from invoice_extraction.application.observability import (
    EventSink,
    JobEvent,
    LlmCallEvent,
    NullSink,
)
from invoice_extraction.application.ports import (
    Example,
    ExtractionModel,
    ExtractionRequest,
    ModelRejectedError,
    ModelReply,
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
    grounding: GroundingRate | None = None  # informational; never blocks


@dataclass(frozen=True)
class RetryPolicy:
    """Short in-process retries for transient 429/503; SQS handles long outages."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0


@dataclass
class _Run:
    """Counters for the `job` wide event; mutated by the nodes of one run."""

    job_id: str | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    repairs: int = 0
    escalated: bool = False
    fell_back: bool = False


class _State(TypedDict, total=False):
    run: _Run
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
        sink: EventSink | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._pre = pre
        self._model = model
        self._post = post
        self._bundle = bundle
        self._retry = retry or RetryPolicy()
        self._max_repairs = max_repairs
        self._sleep = sleep
        self._rng = rng
        self._sink = sink or NullSink()
        self._clock = clock
        self._schema = model_schema()
        self.graph = self._build_graph()

    def __call__(self, pdf: bytes, job_id: str | None = None) -> PipelineResult:
        run = _Run(job_id=job_id)
        started = self._clock()
        try:
            state = self.graph.invoke(
                {"pdf": pdf, "tier": "primary", "repairs_used": 0, "run": run}
            )
        except ModelUnavailableError:
            self._emit_job(run, started, "unavailable")
            raise
        except Exception:
            self._emit_job(run, started, "error")
            raise
        result = replace(state["result"], prompt_version=self._bundle.version)
        self._emit_job(run, started, result.status.value, result)
        return result

    def _emit_job(
        self, run: _Run, started: float, outcome: str, result: PipelineResult | None = None
    ) -> None:
        grounding = result.grounding if result else None
        self._sink.emit(
            JobEvent(
                outcome=outcome,
                duration_ms=(self._clock() - started) * 1000,
                prompt_version=self._bundle.version,
                llm_calls=run.llm_calls,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                repairs=run.repairs,
                escalated=run.escalated,
                fell_back=run.fell_back,
                model=result.model if result else None,
                reason=result.reason.value if result and result.reason else None,
                job_id=run.job_id,
                grounding_rate=grounding.rate if grounding else None,
                grounded_fields=grounding.grounded if grounding else None,
                total_fields=grounding.total if grounding else None,
                ungrounded_fields=grounding.ungrounded if grounding else (),
            )
        )

    # --- graph ---------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(_State)
        graph.add_node("pre", self._pre_node)
        graph.add_node("call", self._call_node)
        graph.add_node("fall_back", self._fall_back_node)
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

    @staticmethod
    def _fall_back_node(state: _State) -> _State:
        state["run"].fell_back = True
        return {"tier": "fallback"}

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
            started = self._clock()
            try:
                reply = self._model.extract(request)
            except ModelRejectedError:
                self._record_call(state, request, attempt, "rejected", started)
                break
            except TransientModelError:
                self._record_call(state, request, attempt, "transient_error", started)
                if attempt + 1 < self._retry.max_attempts:
                    self._sleep(self._backoff(attempt))
            else:
                self._record_call(state, request, attempt, "ok", started, reply)
                return {"raw": reply.data, "call_ok": True, "model": setting.name}
        if state["tier"] == "escalation":
            # the quality model is a bonus: its outage ends the job as a validation failure
            return {"call_ok": False, "result": self._schema_invalid(state)}
        return {"call_ok": False}

    def _record_call(
        self,
        state: _State,
        request: ExtractionRequest,
        attempt: int,
        outcome: str,
        started: float,
        reply: ModelReply | None = None,
    ) -> None:
        run = state["run"]
        run.llm_calls += 1
        input_tokens = reply.input_tokens if reply else None
        output_tokens = reply.output_tokens if reply else None
        run.input_tokens += input_tokens or 0
        run.output_tokens += output_tokens or 0
        self._sink.emit(
            LlmCallEvent(
                model=request.model,
                tier=state["tier"],
                attempt=attempt + 1,
                repair=request.repair is not None,
                outcome=outcome,
                latency_ms=(self._clock() - started) * 1000,
                prompt_version=self._bundle.version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                job_id=run.job_id,
            )
        )

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
                JobStatus.SUCCEEDED,
                extraction=extraction,
                model=state["model"],
                grounding=grounding_rate(state["restored"], state["prepared"].text),
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
        state["run"].repairs += 1
        return {"repair": repair, "repairs_used": state["repairs_used"] + 1}

    @staticmethod
    def _escalate_node(state: _State) -> _State:
        state["run"].escalated = True
        return {"tier": "escalation", "escalated": True, "repairs_used": 0, "repair": None}

    @staticmethod
    def _unavailable_node(state: _State) -> _State:
        raise ModelUnavailableError("primary and fallback models are unavailable")
