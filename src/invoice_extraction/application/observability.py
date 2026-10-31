"""Wide events: one `llm_call` per model call and one `job` per job.

Events hold identifiers, counts, timings and enum-like labels only. They never hold
invoice content (text, values, error messages): the privacy test enforces it. The
`EventSink` port is how the use case emits them; adapters decide the format.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LlmCallEvent:
    model: str
    tier: str  # primary | fallback | escalation
    attempt: int  # 1-based try within this model request
    repair: bool
    outcome: str  # ok | transient_error | rejected
    latency_ms: float
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    job_id: str | None = None


@dataclass(frozen=True)
class JobEvent:
    outcome: str  # a JobStatus value, or "unavailable" / "error"
    duration_ms: float
    prompt_version: str
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    repairs: int = 0
    escalated: bool = False
    fell_back: bool = False
    model: str | None = None
    reason: str | None = None
    job_id: str | None = None
    # informational, over non-anonymized fields; field paths only, never values
    grounding_rate: float | None = None
    grounded_fields: int | None = None
    total_fields: int | None = None
    ungrounded_fields: tuple[str, ...] = ()


WideEvent = LlmCallEvent | JobEvent


class EventSink(Protocol):
    def emit(self, event: WideEvent) -> None:
        """Record one wide event. Must never raise into the pipeline."""


class NullSink:
    def emit(self, event: WideEvent) -> None:
        pass
