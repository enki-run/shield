import hmac
import hashlib
from dataclasses import dataclass
from app.pipeline.detector import DetectedEntity


@dataclass
class MappingRecord:
    pseudonym: str
    original_value: str
    entity_type: str


class Pseudonymizer:
    def __init__(self, doc_key: str):
        self.doc_key = doc_key.encode("utf-8")
        self._cache: dict[str, str] = {}

    def pseudonymize(self, entity: DetectedEntity) -> str:
        cache_key = f"{entity.entity_type}:{entity.text}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        mac = hmac.new(self.doc_key, cache_key.encode("utf-8"), hashlib.sha256)
        short_hash = mac.hexdigest()[:8].upper()
        pseudonym = f"{entity.entity_type}-{short_hash}"
        self._cache[cache_key] = pseudonym
        return pseudonym

    def apply(
        self, text: str, entities: list[DetectedEntity]
    ) -> tuple[str, list[MappingRecord]]:
        mappings: dict[str, MappingRecord] = {}
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
        for entity in sorted_entities:
            pseudonym = self.pseudonymize(entity)
            text = text[: entity.start] + pseudonym + text[entity.end :]
            if pseudonym not in mappings:
                mappings[pseudonym] = MappingRecord(
                    pseudonym=pseudonym,
                    original_value=entity.text,
                    entity_type=entity.entity_type,
                )
        return text, list(mappings.values())
