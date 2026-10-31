"""The Prompt Bundle: system prompt, few-shots, repair prompt and model settings.

Its Prompt Version is a content hash, so every result traces back to exact prompt text.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ModelSetting:
    name: str
    # None: the model rejects the parameter, so it is omitted from the request
    temperature: float | None


@dataclass(frozen=True)
class FewShot:
    invoice_no: str
    text: str
    extraction: dict[str, Any]


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    repair_prompt: str
    examples: tuple[FewShot, ...]
    primary: ModelSetting
    fallback: ModelSetting
    escalation: ModelSetting

    @property
    def version(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
