from odf.opendocument import load
from odf.text import P

from .base import BaseParser, ContentBlock, ParsedContent


class OdtParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        doc = load(file_path)
        blocks = []

        for element in doc.text.getElementsByType(P):
            text = "".join(
                node.data for node in element.childNodes if hasattr(node, "data")
            )
            if text.strip():
                blocks.append(ContentBlock(text=text, block_type="paragraph"))

        return ParsedContent(blocks=blocks, format="odt")
