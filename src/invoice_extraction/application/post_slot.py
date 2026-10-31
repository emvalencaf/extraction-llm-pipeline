"""Post slot: everything done to the model's raw reply before schema validation.

Separate small functions so the graph can wire them as nodes: `guard_output` (reject
malformed or misplaced values), then `restore_output` (exact-string Restore). Normalization
to Decimal and ISO dates stays in the Extraction Schema validators.
"""

import re
import unicodedata
from typing import Any

from invoice_extraction.application.pre_slot import RejectedError
from invoice_extraction.application.privacy import TOKEN, PlaceholderMap, restore_value
from invoice_extraction.domain.status import TerminalReason

MAX_VALUE_LENGTH = 300

# Where each kind of Placeholder may legitimately appear in a raw Extraction.
_ALLOWED_KINDS: dict[str, str] = {
    "seller.name": "NAME",
    "seller.address": "ADDRESS",
    "seller.tax_id": "TAX_ID",
    "client.name": "NAME",
    "client.address": "ADDRESS",
    "client.tax_id": "TAX_ID",
}
_REQUIRED = tuple(_ALLOWED_KINDS)

# A Placeholder the model mangled: bracket or case or separator changed, but still shaped like one.
_ALTERED = re.compile(
    r"\[[A-Za-z_ ]+[_ ]?\d+\]|\b(?:NAME|ADDRESS|TAX_ID|EMAIL|PHONE|ACCOUNT)[_ -]?\d+\b"
)


def _strings(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}" if path else key)


def _problems(raw: dict[str, Any], placeholders: PlaceholderMap) -> list[str]:
    problems: list[str] = []
    known = placeholders.tokens()
    for path, text in _strings(raw):
        if len(text) > MAX_VALUE_LENGTH:
            problems.append(f"{path}: value longer than {MAX_VALUE_LENGTH} characters")
        if any(unicodedata.category(c)[0] == "C" and c not in "\n\t" for c in text):
            problems.append(f"{path}: control characters")
        for match in TOKEN.finditer(text):
            token = match.group(0)
            if token not in known:
                problems.append(f"{path}: unknown placeholder {token}")
            elif _ALLOWED_KINDS.get(path) != match.group(1):
                problems.append(f"{path}: placeholder {token} is not allowed in this field")
        if _ALTERED.search(TOKEN.sub("", text)):
            problems.append(f"{path}: altered placeholder")
    for path in _REQUIRED:
        value = raw
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and not value.strip():
            problems.append(f"{path}: empty")
    return problems


def guard_output(raw: dict[str, Any], placeholders: PlaceholderMap) -> None:
    """Reject a raw reply with leftover, altered or misplaced Placeholders or malformed values."""
    problems = _problems(raw, placeholders)
    if problems:
        raise RejectedError(TerminalReason.OUTPUT_REJECTED, "; ".join(problems))


def restore_output(raw: dict[str, Any], placeholders: PlaceholderMap) -> dict[str, Any]:
    return restore_value(raw, placeholders)


class PostSlot:
    def __call__(self, raw: dict[str, Any], placeholders: PlaceholderMap) -> dict[str, Any]:
        guard_output(raw, placeholders)
        return restore_output(raw, placeholders)
