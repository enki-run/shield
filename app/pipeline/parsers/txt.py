from .base import BaseParser, ContentBlock, ParsedContent


class TxtParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        blocks = [
            ContentBlock(text=line.rstrip("\n"), block_type="paragraph")
            for line in lines
        ]
        return ParsedContent(blocks=blocks, format="txt")
