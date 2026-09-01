"""
Base abstraction for format-specific document processors.

Every concrete processor (PDF, PPTX, DOCX, TXT, Image) implements `process`
and returns a fully-populated `NormalizedDocument`. This keeps the API layer
free of any extraction logic and makes it trivial to add new formats later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from schemas.document import NormalizedDocument


class BaseProcessor(ABC):
    """Abstract interface every format-specific processor must implement."""

    @abstractmethod
    def process(
        self,
        file_path: Path,
        document_id: str,
        filename: str,
    ) -> NormalizedDocument:
        """
        Extract content from `file_path` and return a NormalizedDocument.

        Implementations should raise `processing.exceptions.DocumentProcessingError`
        (or a subclass) if the file is corrupt or cannot be parsed, rather than
        letting raw library exceptions bubble up.
        """
        raise NotImplementedError
