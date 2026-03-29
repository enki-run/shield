from dataclasses import dataclass, field


@dataclass
class ContentBlock:
    text: str
    block_type: str = "paragraph"
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedContent:
    blocks: list[ContentBlock]
    format: str = ""
    metadata: dict = field(default_factory=dict)

    def get_full_text(self) -> str:
        return "\n".join(block.text for block in self.blocks if block.text.strip())


class BaseParser:
    def parse(self, file_path: str) -> ParsedContent:
        raise NotImplementedError
