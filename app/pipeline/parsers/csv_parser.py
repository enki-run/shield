import csv

from .base import BaseParser, ContentBlock, ParsedContent


class CsvParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        blocks = []
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                for col_idx, cell in enumerate(row):
                    blocks.append(
                        ContentBlock(
                            text=cell,
                            block_type="cell",
                            metadata={"row": row_idx, "col": col_idx},
                        )
                    )
        return ParsedContent(blocks=blocks, format="csv")
