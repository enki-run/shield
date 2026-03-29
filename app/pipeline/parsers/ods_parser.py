from odf.opendocument import load
from odf.table import Table, TableCell, TableRow

from .base import BaseParser, ContentBlock, ParsedContent


class OdsParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        doc = load(file_path)
        blocks = []

        for table in doc.spreadsheet.getElementsByType(Table):
            for row in table.getElementsByType(TableRow):
                for cell in row.getElementsByType(TableCell):
                    text = "".join(
                        node.data
                        for node in cell.childNodes
                        if hasattr(node, "data")
                    )
                    # Also check nested P elements
                    if not text:
                        from odf.text import P
                        for p in cell.getElementsByType(P):
                            text += "".join(
                                node.data
                                for node in p.childNodes
                                if hasattr(node, "data")
                            )
                    if text.strip():
                        blocks.append(ContentBlock(text=text, block_type="cell"))

        return ParsedContent(blocks=blocks, format="ods")
