"""
SEPLE PDF Parser
Extracts text and structured data from tender PDF documents.
"""
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFParser:
    """Extracts text content from tender PDF documents."""

    def __init__(self):
        try:
            import pdfplumber
            self._backend = "pdfplumber"
        except ImportError:
            logger.warning("pdfplumber not available, falling back to PyPDF2")
            self._backend = "pypdf2"

    def extract_text(self, pdf_path: str | Path) -> str:
        """
        Extract all text from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text as a single string
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Extracting text from: {pdf_path.name} (backend: {self._backend})")

        if self._backend == "pdfplumber":
            return self._extract_with_pdfplumber(pdf_path)
        else:
            return self._extract_with_pypdf2(pdf_path)

    def extract_text_from_bytes(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes (e.g., downloaded from a URL)."""
        if self._backend == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

    def extract_tables(self, pdf_path: str | Path) -> list[list[list[str]]]:
        """
        Extract tables from a PDF (requires pdfplumber).

        Returns:
            List of tables, where each table is a list of rows,
            and each row is a list of cell values.
        """
        if self._backend != "pdfplumber":
            logger.warning("Table extraction requires pdfplumber")
            return []

        import pdfplumber
        tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)

        logger.info(f"Extracted {len(tables)} tables from {Path(pdf_path).name}")
        return tables

    def _extract_with_pdfplumber(self, pdf_path: Path) -> str:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)

    def _extract_with_pypdf2(self, pdf_path: Path) -> str:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
