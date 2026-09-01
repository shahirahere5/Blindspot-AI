"""PDF processing using PyMuPDF (fitz)."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from processing.base import BaseProcessor
from processing.exceptions import DocumentProcessingError
from schemas.document import (
    ContentBlock,
    ContentBlockType,
    DocumentStatus,
    FileType,
    NormalizedDocument,
)

# If the average extracted characters per page is below this threshold,
# we treat the PDF as likely scanned/image-based (no real text layer).
MIN_CHARS_PER_PAGE_FOR_TEXT = 20


class PDFProcessor(BaseProcessor):
    def process(
        self,
        file_path: Path,
        document_id: str,
        filename: str,
    ) -> NormalizedDocument:
        try:
            pdf = fitz.open(file_path)
        except Exception as exc:  # noqa: BLE001 - library raises generic errors
            raise DocumentProcessingError(f"Could not open PDF: {exc}") from exc

        try:
            page_count = pdf.page_count
            content: list[ContentBlock] = []
            total_chars = 0

            for index in range(page_count):
                page = pdf.load_page(index)
                text = page.get_text("text").strip()
                total_chars += len(text)
                content.append(
                    ContentBlock(
                        type=ContentBlockType.PAGE,
                        location=index + 1,
                        text=text,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            raise DocumentProcessingError(f"Failed to extract PDF text: {exc}") from exc
        finally:
            pdf.close()

        avg_chars_per_page = total_chars / page_count if page_count else 0
        warnings: list[str] = []

        if page_count > 0 and avg_chars_per_page < MIN_CHARS_PER_PAGE_FOR_TEXT:
            # Likely a scanned PDF with no extractable text layer.
            return NormalizedDocument(
                document_id=document_id,
                filename=filename,
                file_type=FileType.PDF,
                status=DocumentStatus.REQUIRES_MULTIMODAL_PROCESSING,
                content=content,
                metadata={"page_count": page_count},
                warnings=[
                    "Little to no extractable text was found. "
                    "This PDF likely requires OCR/multimodal processing "
                    "in a later phase."
                ],
            )

        return NormalizedDocument(
            document_id=document_id,
            filename=filename,
            file_type=FileType.PDF,
            status=DocumentStatus.PROCESSED,
            content=content,
            metadata={"page_count": page_count},
            warnings=warnings,
        )
