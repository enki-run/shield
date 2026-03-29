import csv

from .base import BaseParser, ContentBlock, ParsedContent


class CsvParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        blocks = []
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                for col_idx, cell in enumerate(row):
                    if not cell.strip():
                        continue
                    skip = row_idx == 0  # Header row
                    blocks.append(
                        ContentBlock(
                            text=cell,
                            block_type="cell",
                            metadata={
                                "row": row_idx,
                                "col": col_idx,
                                "skip_detection": skip,
                            },
                        )
                    )
        return ParsedContent(blocks=blocks, format="csv")
