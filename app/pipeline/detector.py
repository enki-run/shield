"""
PII Detection Engine — the heart of Shield.

Detection pipeline:
  1. spaCy NER (de_core_news_lg) — contextual entity recognition
  2. Presidio built-in recognizers — pattern-based (EMAIL, IBAN, PHONE, etc.)
  3. Config-based rules (detection_rules.json) — editable without code changes
  4. Deduplication — resolve overlapping entities, highest confidence wins

Rules are loaded from detection_rules.json at startup. To tune detection:
  - Edit detection_rules.json (add patterns, adjust scores, add context words)
  - Restart the service
  - No code changes needed
"""

import json
import os
from dataclasses import dataclass

import structlog
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

logger = structlog.get_logger()

RULES_PATH = os.path.join(os.path.dirname(__file__), "detection_rules.json")


@dataclass
class DetectedEntity:
    entity_type: str
    text: str
    start: int
    end: int
    confidence: float
    recognizer: str


def _load_rules(path: str = RULES_PATH) -> dict:
    """Load detection rules from JSON config file."""
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


def _build_recognizers_from_rules(config: dict) -> list[PatternRecognizer]:
    """Create Presidio PatternRecognizers from config rules."""
    recognizers = []
    for rule in config.get("rules", []):
        patterns = [
            Pattern(name=p["name"], regex=p["regex"], score=p["score"])
            for p in rule.get("patterns", [])
        ]
        if not patterns:
            continue
        recognizer = PatternRecognizer(
            supported_entity=rule["entity_type"],
            name=rule["name"],
            supported_language="de",
            patterns=patterns,
            context=rule.get("context", []),
        )
        recognizers.append(recognizer)
    logger.info(
        "detection.rules_loaded",
        rule_count=len(recognizers),
        rules=[r["name"] for r in config.get("rules", [])],
    )
    return recognizers


_analyzer_engine = None
_dedup_config = {}


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer_engine, _dedup_config
    if _analyzer_engine is None:
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "de", "model_name": "de_core_news_lg"}],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        _analyzer_engine = AnalyzerEngine(
            nlp_engine=nlp_engine, supported_languages=["de"]
        )

        # Load and register config-based rules
        rules_config = _load_rules()
        _dedup_config = rules_config.get("entity_dedup", {})
        for recognizer in _build_recognizers_from_rules(rules_config):
            _analyzer_engine.registry.add_recognizer(recognizer)

    return _analyzer_engine


BALANCED_ENTITIES = [
    "PERSON",
    "ORGANIZATION",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "IBAN_CODE",
    "CREDIT_CARD",
    "LOCATION",
    "IP_ADDRESS",
    "URL",
]
COMPLIANT_ENTITIES = BALANCED_ENTITIES + [
    "NRP",
    "DATE_TIME",
    "MEDICAL_LICENSE",
    "US_SSN",
]
CONFIDENCE_THRESHOLDS = {"balanced": 0.7, "compliant": 0.5}


class PiiDetector:
    def __init__(self, mode: str = "balanced"):
        self.mode = mode
        self.threshold = CONFIDENCE_THRESHOLDS.get(mode, 0.7)
        self.entities = (
            COMPLIANT_ENTITIES if mode == "compliant" else BALANCED_ENTITIES
        )
        self.analyzer = _get_analyzer()

    def detect(self, text: str) -> list[DetectedEntity]:
        results = self.analyzer.analyze(
            text=text,
            language="de",
            entities=self.entities,
            score_threshold=self.threshold,
        )

        raw = [
            DetectedEntity(
                entity_type=r.entity_type,
                text=text[r.start : r.end],
                start=r.start,
                end=r.end,
                confidence=r.score,
                recognizer=(
                    r.recognition_metadata.get("recognizer_name", "unknown")
                    if r.recognition_metadata
                    else "unknown"
                ),
            )
            for r in results
        ]

        cleaned = [_trim_entity(e, text) for e in raw]
        entities = _deduplicate_entities(cleaned, _dedup_config)
        entities.sort(key=lambda e: e.start)
        return entities


_ORG_LEGAL_SUFFIXES = {"gmbh", "mbh", "ag", "kg", "ohg", "se", "ggmbh", "ug", "e.v.", "ev", "ltd", "inc"}
_NOISE_WORDS = {
    "der", "die", "das", "dem", "den", "des", "ein", "eine", "einem", "einen",
    "und", "oder", "mit", "bei", "von", "vom", "zum", "zur", "auf", "in", "an",
    "für", "über", "unter", "nach", "vor", "aus", "zu",
    "ist", "sind", "war", "hat", "haben", "wird", "werden",
    "ich", "mein", "meine", "wir", "unser", "unsere",
    "hiermit", "fristgerecht", "ordentlich", "nächstmöglichen",
}


def _trim_entity(entity: DetectedEntity, full_text: str) -> DetectedEntity:
    """Trim noise words from start/end of ORGANIZATION entities.
    spaCy often includes surrounding words like 'der', 'fristgerecht' etc."""
    if entity.entity_type != "ORGANIZATION":
        return entity

    words = entity.text.split()
    if len(words) <= 1:
        return entity

    # Trim leading words until we find a known org keyword or legal suffix.
    # This removes spaCy's tendency to include preceding sentence fragments.
    _ORG_KEYWORDS = {"institut", "verein", "stiftung", "verband", "akademie", "zentrum",
                     "amt", "behörde", "ministerium", "gesellschaft"}
    # Find the first word that's a known org keyword or legal suffix
    keyword_idx = None
    for i, w in enumerate(words):
        wl = w.lower().rstrip(".,;:")
        if wl in _ORG_KEYWORDS or wl in _ORG_LEGAL_SUFFIXES:
            keyword_idx = i
            break

    if keyword_idx is not None and keyword_idx > 0:
        # Keep up to 3 capitalized words before the keyword (likely the org prefix)
        prefix_start = max(0, keyword_idx - 3)
        # Only keep prefix words that start with an uppercase letter
        while prefix_start < keyword_idx:
            if words[prefix_start][0].isupper():
                break
            prefix_start += 1
        words = words[prefix_start:]
    else:
        # No keyword found — just trim noise words from front
        while len(words) > 1 and words[0].lower().rstrip(".,;:") in _NOISE_WORDS:
            words = words[1:]

    # Trim trailing noise — stop at legal suffix, otherwise trim lowercase non-org words
    has_legal_suffix = words[-1].lower().rstrip(".") in _ORG_LEGAL_SUFFIXES
    if not has_legal_suffix:
        while len(words) > 1 and words[-1].lower().rstrip(".,;:") in _NOISE_WORDS:
            words = words[:-1]
        # Also trim trailing words that start with lowercase and aren't part of known org patterns
        while len(words) > 2 and words[-1][0].islower() and words[-1].lower() not in {"für", "der", "des", "zu"}:
            words = words[:-1]

    trimmed_text = " ".join(words)
    # Recalculate start position
    new_start = full_text.find(trimmed_text, entity.start)
    if new_start == -1:
        new_start = entity.start
    new_end = new_start + len(trimmed_text)

    return DetectedEntity(
        entity_type=entity.entity_type,
        text=trimmed_text,
        start=new_start,
        end=new_end,
        confidence=entity.confidence,
        recognizer=entity.recognizer,
    )


def _deduplicate_entities(
    entities: list[DetectedEntity], dedup_config: dict
) -> list[DetectedEntity]:
    """Remove overlapping entities. Higher confidence wins. Type priority breaks ties."""
    if not entities:
        return []

    type_priority = dedup_config.get("type_priority", {})
    sorted_ents = sorted(
        entities,
        key=lambda e: (-e.confidence, type_priority.get(e.entity_type, 5)),
    )

    kept = []
    for candidate in sorted_ents:
        overlaps = any(
            candidate.start < ex.end and candidate.end > ex.start for ex in kept
        )
        if not overlaps:
            kept.append(candidate)

    return kept
