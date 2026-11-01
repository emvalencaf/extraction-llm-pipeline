"""SensitiveDetector backed by Presidio with custom Indian-invoice recognizers.

Presidio runs on a blank spaCy pipeline (tokenizer only): no model download, no network,
deterministic. Detection is therefore pattern based (GSTIN, PAN, US-SSN-like tax ids, email,
phone, IFSC, bank account, company names by legal suffix, labeled values, Indian postal
addresses). Free-form person names without a label need a statistical NER model; pass
`spacy_model="en_core_web_sm"` (installed separately) to add Presidio's PERSON/LOCATION
entities on top. Presidio and spaCy live only in this adapter.
"""

import itertools
import re
from collections.abc import Iterable

import spacy
from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpArtifacts, SpacyNlpEngine

from invoice_extraction.application.ports import SensitiveSpan

_LANG = "en"
_SCORE = 0.85
_PERSON_MODEL_KINDS = {"PERSON": "NAME", "LOCATION": "ADDRESS", "ORGANIZATION": "NAME"}

_SUFFIX = r"(?:Pvt\.?[ ]+Ltd\.?|Private[ ]+Limited|Limited|Ltd\.?|LLP|LLC|Inc\.?|Corp\.?)(?![\w])"
_COMPANY = re.compile(
    r"(?:(?!(?:Pvt|Private|Ltd|Limited|LLP|LLC|Inc|Corp)\b)[A-Z][\w&.'-]*[ ]+){1,5}" + _SUFFIX
)

_WORD = r"[A-Z][a-z]+(?: [A-Z][a-z]+)*"
_POSTAL = re.compile(rf"{_WORD}(?:,[ ]*{_WORD})?[ ]*[-,]?[ ]*(?<![\d.,])\d{{6}}(?![.,]?\d)")
_SEGMENT_START = re.compile(r"(?<= )\d+[A-Za-z/-]*(?= [A-Z])")

_LABELED: dict[str, list[str]] = {
    "TAX_ID": [
        r"(?i:Tax[ ]*Id|GSTIN|GST[ ]*No\.?|PAN|VAT[ ]*No\.?)[ ]*:[ ]*"
        r"(?P<value>[A-Z0-9][A-Z0-9-]{5,})"
    ],
    "NAME": [
        r"(?i:Contact|Attn|Attention|Bill[ ]*to|Ship[ ]*to)[ ]*:[ ]*"
        r"(?P<value>[A-Z][\w.'-]*(?:[ ][A-Z][\w.'-]*){0,3})"
    ],
    "ACCOUNT": [
        r"(?i:A/c(?:[ ]*No\.?)?|Account(?:[ ]*(?:No\.?|Number))?|Acct\.?(?:[ ]*No\.?)?)"
        r"[ ]*:?[ ]*(?P<value>\d[\d -]{6,20}\d)"
    ],
    "PHONE": [r"(?i:Phone|Ph|Tel|Mobile|Mob)\.?[ ]*:[ ]*(?P<value>\+?\d[\d ()-]{6,18}\d)"],
}


class _Recognizer(EntityRecognizer):
    """Base: no model to load; subclasses implement `_spans`."""

    def __init__(self, entities: list[str], name: str) -> None:
        super().__init__(supported_entities=entities, supported_language=_LANG, name=name)

    def load(self) -> None:
        return None

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        return [RecognizerResult(kind, s, e, _SCORE) for kind, s, e in self._spans(text)]

    def _spans(self, text: str) -> Iterable[tuple[str, int, int]]:
        raise NotImplementedError


class _LabeledValueRecognizer(_Recognizer):
    """Values that follow a label such as `Tax Id:` or `A/c No`; the label is kept."""

    def __init__(self) -> None:
        super().__init__(list(_LABELED), "labeled-values")
        self._patterns = [
            (kind, re.compile(p)) for kind, patterns in _LABELED.items() for p in patterns
        ]

    def _spans(self, text):
        for kind, pattern in self._patterns:
            for match in pattern.finditer(text):
                yield kind, match.start("value"), match.end("value")


class _CompanyRecognizer(_Recognizer):
    def __init__(self) -> None:
        super().__init__(["NAME"], "company-names")

    def _spans(self, text):
        for match in _COMPANY.finditer(text):
            yield "NAME", match.start(), match.end()


class _PostalAddressRecognizer(_Recognizer):
    """Indian postal lines (`City, State - 400093`) and the street line above them.

    Invoices print Seller and Client side by side, so one text line holds two parties.
    A line with k postal segments splits the street line above into k addresses, cut
    before a token that starts a house number (`... East 42 MG Road`). When the cuts do
    not line up, the whole street line becomes one address (over-redacting, never leaking).
    """

    def __init__(self) -> None:
        super().__init__(["ADDRESS"], "postal-addresses")

    def _spans(self, text):
        lines = [(m.start(), m.group(0)) for m in re.finditer(r"[^\n]+", text)]
        for index, (offset, line) in enumerate(lines):
            postal = list(_POSTAL.finditer(line))
            for match in postal:
                yield "ADDRESS", offset + match.start(), offset + match.end()
            if postal and index > 0:
                yield from self._street(*lines[index - 1], parts=len(postal))

    @staticmethod
    def _street(offset: int, line: str, parts: int):
        if ":" in line or not any(c.isdigit() for c in line) or _POSTAL.search(line):
            return
        starts = [m.start() for m in _SEGMENT_START.finditer(line)]
        cuts = starts[-(parts - 1) :] if parts > 1 and len(starts) >= parts - 1 else []
        edges = [0, *cuts, len(line)]
        for begin, end in itertools.pairwise(edges):
            piece = line[begin:end]
            stripped = piece.strip()
            if stripped:
                start = offset + begin + (len(piece) - len(piece.lstrip()))
                yield "ADDRESS", start, start + len(stripped)


class _BlankSpacyEngine(SpacyNlpEngine):
    """Tokenizer-only spaCy pipeline, or a real model when one is requested."""

    def __init__(self, spacy_model: str | None) -> None:
        super().__init__(models=[{"lang_code": _LANG, "model_name": spacy_model or "blank"}])
        self._model = spacy_model

    def load(self) -> None:
        pipeline = spacy.load(self._model) if self._model else spacy.blank(_LANG)
        if not pipeline.has_pipe("sentencizer") and not pipeline.has_pipe("parser"):
            pipeline.add_pipe("sentencizer")
        self.nlp = {_LANG: pipeline}


def _pattern(entity: str, name: str, regex: str) -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=entity,
        name=name,
        supported_language=_LANG,
        patterns=[Pattern(name, regex, _SCORE)],
    )


def _recognizers() -> list[EntityRecognizer]:
    return [
        _pattern("TAX_ID", "gstin", r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
        _pattern("TAX_ID", "pan", r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        _pattern("TAX_ID", "us-ssn-like", r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])"),
        _pattern("EMAIL", "email", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
        _pattern(
            "PHONE", "indian-mobile", r"(?<![\d.,])(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?![\d.,])"
        ),
        _pattern("PHONE", "intl-phone", r"(?<![\w])\+\d{1,3}[ -]?\d[\d -]{7,12}\d(?!\d)"),
        _pattern("ACCOUNT", "ifsc", r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        _pattern("ACCOUNT", "bank-account", r"(?<![\d.,])\d{9,18}(?![\d.,])"),
        _LabeledValueRecognizer(),
        _CompanyRecognizer(),
        _PostalAddressRecognizer(),
    ]


class PresidioDetector:
    def __init__(self, spacy_model: str | None = None) -> None:
        registry = RecognizerRegistry(supported_languages=[_LANG])
        for recognizer in _recognizers():
            registry.add_recognizer(recognizer)
        self._engine = AnalyzerEngine(
            registry=registry,
            nlp_engine=_BlankSpacyEngine(spacy_model),
            supported_languages=[_LANG],
        )
        self._with_ner = spacy_model is not None

    def detect(self, text: str) -> list[SensitiveSpan]:
        results = self._engine.analyze(text=text, language=_LANG)
        spans = []
        for result in results:
            kind = _PERSON_MODEL_KINDS.get(result.entity_type, result.entity_type)
            if kind in {"NAME", "ADDRESS", "TAX_ID", "EMAIL", "PHONE", "ACCOUNT"}:
                spans.append(SensitiveSpan(result.start, result.end, kind))
        return spans
