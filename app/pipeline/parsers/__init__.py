from .base import BaseParser, ContentBlock, ParsedContent

SUPPORTED_FORMATS = {"txt", "csv", "docx", "xlsx", "odt", "ods", "pdf"}

FORMAT_EXTENSIONS = {
    ".txt": "txt",
    ".csv": "csv",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".odt": "odt",
    ".ods": "ods",
    ".pdf": "pdf",
}


def get_parser(format: str) -> BaseParser:
    """Return the appropriate parser for the given format string.

    Raises ValueError for unsupported formats.
    """
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: '{format}'. "
            f"Supported formats: {sorted(SUPPORTED_FORMATS)}"
        )

    if fmt == "txt":
        from .txt import TxtParser
        return TxtParser()
    elif fmt == "csv":
        from .csv_parser import CsvParser
        return CsvParser()
    elif fmt == "docx":
        from .docx_parser import DocxParser
        return DocxParser()
    elif fmt == "xlsx":
        from .xlsx_parser import XlsxParser
        return XlsxParser()
    elif fmt == "odt":
        from .odt_parser import OdtParser
        return OdtParser()
    elif fmt == "ods":
        from .ods_parser import OdsParser
        return OdsParser()
    elif fmt == "pdf":
        from .pdf_parser import PdfParser
        return PdfParser()

    # Should never reach here given the check above
    raise ValueError(f"Unsupported format: '{format}'")


__all__ = [
    "BaseParser",
    "ContentBlock",
    "ParsedContent",
    "SUPPORTED_FORMATS",
    "FORMAT_EXTENSIONS",
    "get_parser",
]
