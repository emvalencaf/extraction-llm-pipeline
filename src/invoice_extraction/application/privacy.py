"""Anonymization and Restore with an in-memory Placeholder map.

Placeholders look like `[TYPE_n]` (validated in docs/experiments/gemini-placeholder-
preservation.md). The map lives only for one job: it is never logged, pickled or
serialized, and its repr hides the values it holds.
"""

import re
from typing import Any, NoReturn

from invoice_extraction.application.ports import SensitiveSpan

TOKEN = re.compile(r"\[([A-Z_]+)_(\d+)\]")


class PlaceholderMap:
    """Bijection between sensitive values and `[TYPE_n]` tokens, for one job."""

    __slots__ = ("_by_token", "_by_value", "_counts")

    def __init__(self) -> None:
        self._by_token: dict[str, str] = {}
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def placeholder_for(self, kind: str, value: str) -> str:
        """One Placeholder per distinct value, numbered by first appearance within a type."""
        key = (kind, value)
        if key not in self._by_value:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            token = f"[{kind}_{self._counts[kind]}]"
            self._by_value[key] = token
            self._by_token[token] = value
        return self._by_value[key]

    def value_of(self, token: str) -> str | None:
        return self._by_token.get(token)

    def tokens(self) -> set[str]:
        return set(self._by_token)

    def __len__(self) -> int:
        return len(self._by_token)

    def __repr__(self) -> str:
        return f"PlaceholderMap(<{len(self)} placeholders, values hidden>)"

    __str__ = __repr__

    def __reduce__(self) -> NoReturn:
        raise TypeError("PlaceholderMap must never be persisted")

    def __getstate__(self) -> NoReturn:
        raise TypeError("PlaceholderMap must never be persisted")


def _resolve_overlaps(spans: list[SensitiveSpan]) -> list[SensitiveSpan]:
    """Keep the earliest, then longest, span of each overlapping group."""
    kept: list[SensitiveSpan] = []
    for span in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if not kept or span.start >= kept[-1].end:
            kept.append(span)
    return kept


def anonymize(text: str, spans: list[SensitiveSpan]) -> tuple[str, PlaceholderMap]:
    placeholders = PlaceholderMap()
    out: list[str] = []
    cursor = 0
    for span in _resolve_overlaps(spans):
        out.append(text[cursor : span.start])
        out.append(placeholders.placeholder_for(span.kind, text[span.start : span.end]))
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out), placeholders


def restore_value(value: Any, placeholders: PlaceholderMap) -> Any:
    """Exact-string Restore of every known token in every string of a raw Extraction."""
    if isinstance(value, str):
        return TOKEN.sub(lambda m: placeholders.value_of(m.group(0)) or m.group(0), value)
    if isinstance(value, list):
        return [restore_value(v, placeholders) for v in value]
    if isinstance(value, dict):
        return {k: restore_value(v, placeholders) for k, v in value.items()}
    return value
