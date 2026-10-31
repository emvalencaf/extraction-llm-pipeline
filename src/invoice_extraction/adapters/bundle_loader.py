"""Load the Prompt Bundle shipped inside the package (no runtime prompt service)."""

import json
from functools import cache
from importlib import resources

from invoice_extraction.application.prompt_bundle import FewShot, ModelSetting, PromptBundle


def _setting(raw: dict) -> ModelSetting:
    return ModelSetting(name=raw["name"], temperature=raw["temperature"])


@cache
def load_bundle() -> PromptBundle:
    """Read the bundle once per process (cold start); it is immutable."""
    root = resources.files("invoice_extraction") / "prompts"
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    examples = json.loads((root / "examples.json").read_text(encoding="utf-8"))
    return PromptBundle(
        system_prompt=(root / "system.md").read_text(encoding="utf-8"),
        repair_prompt=(root / "repair.md").read_text(encoding="utf-8"),
        examples=tuple(FewShot(e["invoice_no"], e["text"], e["extraction"]) for e in examples),
        primary=_setting(settings["primary"]),
        fallback=_setting(settings["fallback"]),
        escalation=_setting(settings["escalation"]),
    )
