"""Plain text processing with safe encoding fallback."""

from __future__ import annotations

from pathlib import Path

from processing.base import BaseProcessor
from processing.exceptions import DocumentProcessingError
from schemas.document import (
    ContentBlock,
    ContentBlockType,
    DocumentStatus,
    FileType,
    NormalizedDocument,
)


class TXTProcessor(BaseProcessor):
    def process(
        self,
        file_path: Path,
        document_id: str,
        filename: str,
    ) -> NormalizedDocument:
        raw_bytes = file_path.read_bytes()

        text, used_fallback = self._decode_safely(raw_bytes)

        if not text.strip():
            raise DocumentProcessingError("TXT file contains no readable text.")

        content = [
            ContentBlock(
                type=ContentBlockType.TEXT,
                location=1,
                text=text,
            )
        ]

        warnings = []
        if used_fallback:
            warnings.append(
                "File was not valid UTF-8; decoded using a fallback encoding "
                "and invalid bytes were replaced."
            )

        return NormalizedDocument(
            document_id=document_id,
            filename=filename,
            file_type=FileType.TXT,
            status=DocumentStatus.PROCESSED,
            content=content,
            metadata={"character_count": len(text)},
            warnings=warnings,
        )

    @staticmethod
    def _decode_safely(raw_bytes: bytes) -> tuple[str, bool]:
        """Try UTF-8 first, then fall back to latin-1 with replacement."""
        try:
            return raw_bytes.decode("utf-8"), False
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="replace"), True
