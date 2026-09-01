"""Factory that maps a normalized file_type to its processor implementation."""

from __future__ import annotations

from processing.base import BaseProcessor
from processing.docx import DOCXProcessor
from processing.exceptions import UnsupportedFileTypeError
from processing.image import ImageProcessor
from processing.pdf import PDFProcessor
from processing.pptx import PPTXProcessor
from processing.txt import TXTProcessor

_PROCESSORS: dict[str, BaseProcessor] = {
    "pdf": PDFProcessor(),
    "pptx": PPTXProcessor(),
    "docx": DOCXProcessor(),
    "txt": TXTProcessor(),
    "image": ImageProcessor(),
}


def get_processor(file_type: str) -> BaseProcessor:
    processor = _PROCESSORS.get(file_type)
    if processor is None:
        raise UnsupportedFileTypeError(f"No processor registered for '{file_type}'.")
    return processor
