import pdfplumber

from .base import BaseParser, ContentBlock, ParsedContent


class PdfParser(BaseParser):
    def parse(self, file_path: str) -> ParsedContent:
        blocks = []

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return ParsedContent(blocks=blocks, format="pdf")

            pages_with_text = 0
            page_results = []

            for page in pdf.pages:
                page_blocks = []

                # Extract tables first
                tables = page.extract_tables()
                table_bboxes = []
                for table_data in tables:
                    if not table_data:
                        continue
                    # Build markdown table
                    rows_md = []
                    for i, row in enumerate(table_data):
                        cells = [str(cell) if cell is not None else "" for cell in row]
                        rows_md.append("| " + " | ".join(cells) + " |")
                        if i == 0:
                            rows_md.append(
                                "| " + " | ".join(["---"] * len(cells)) + " |"
                            )
                    md = "\n".join(rows_md)
                    page_blocks.append(
                        ContentBlock(text=md, block_type="table")
                    )

                # Extract text lines
                text = page.extract_text()
                if text and text.strip():
                    pages_with_text += 1
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            page_blocks.append(
                                ContentBlock(text=line, block_type="paragraph")
                            )

                page_results.append(page_blocks)

            # Scanned PDF detection: less than 50% of pages have extractable text
            text_ratio = pages_with_text / total_pages
            if text_ratio < 0.5:
                raise ValueError(
                    f"Scanned PDF detected: only {pages_with_text} of {total_pages} "
                    f"pages ({text_ratio:.0%}) contain extractable text. "
                    "Please use OCR to convert the PDF before processing."
                )

            for page_blocks in page_results:
                blocks.extend(page_blocks)

        return ParsedContent(blocks=blocks, format="pdf")
