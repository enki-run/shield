from openpyxl import load_workbook

from .base import BaseParser, ContentBlock, ParsedContent


class XlsxParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        blocks = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row_idx, row in enumerate(ws.iter_rows()):
                for col_idx, cell in enumerate(row):
                    if cell.value is not None:
                        blocks.append(
                            ContentBlock(
                                text=str(cell.value),
                                block_type="cell",
                                metadata={
                                    "sheet": sheet_name,
                                    "row": row_idx,
                                    "col": col_idx,
                                },
                            )
                        )

        wb.close()
        return ParsedContent(blocks=blocks, format="xlsx")
