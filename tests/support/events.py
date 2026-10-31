"""Test sinks for the wide events."""

from invoice_extraction.application.observability import JobEvent, LlmCallEvent

Event = LlmCallEvent | JobEvent


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    @property
    def llm_calls(self) -> list[LlmCallEvent]:
        return [e for e in self.events if isinstance(e, LlmCallEvent)]

    @property
    def jobs(self) -> list[JobEvent]:
        return [e for e in self.events if isinstance(e, JobEvent)]
