"""Unit tests for format-specific processors (extraction logic in isolation)."""

from __future__ import annotations

from pathlib import Path

from processing.docx import DOCXProcessor
from processing.image import ImageProcessor
from processing.pdf import PDFProcessor
from processing.pptx import PPTXProcessor
from processing.txt import TXTProcessor
from schemas.document import DocumentStatus


def test_pdf_extraction_preserves_page_boundaries(tmp_path, sample_pdf_bytes):
    path = tmp_path / "test.pdf"
    path.write_bytes(sample_pdf_bytes)

    document = PDFProcessor().process(path, "doc_1", "test.pdf")

    assert document.status == DocumentStatus.PROCESSED
    assert document.metadata["page_count"] == 3
    assert len(document.content) == 3
    assert document.content[0].location == 1
    assert "page 1" in document.content[0].text.lower()


def test_pptx_extraction_preserves_slide_boundaries(tmp_path, sample_pptx_bytes):
    path = tmp_path / "test.pptx"
    path.write_bytes(sample_pptx_bytes)

    document = PPTXProcessor().process(path, "doc_2", "test.pptx")

    assert document.status == DocumentStatus.PROCESSED
    assert len(document.content) == 2
    assert document.content[0].location == 1
    assert document.content[0].extra.get("title") == "Our Pitch"


def test_docx_extraction_includes_tables(tmp_path, sample_docx_bytes):
    path = tmp_path / "test.docx"
    path.write_bytes(sample_docx_bytes)

    document = DOCXProcessor().process(path, "doc_3", "test.docx")

    assert document.status == DocumentStatus.PROCESSED
    table_blocks = [b for b in document.content if b.type.value == "table"]
    assert len(table_blocks) == 1
    assert "Header A" in table_blocks[0].text


def test_txt_extraction(tmp_path, sample_txt_bytes):
    path = tmp_path / "test.txt"
    path.write_bytes(sample_txt_bytes)

    document = TXTProcessor().process(path, "doc_4", "test.txt")

    assert document.status == DocumentStatus.PROCESSED
    assert len(document.content) == 1
    assert "Hello Blind Spot AI" in document.content[0].text


def test_image_metadata_extraction(tmp_path, sample_png_bytes):
    path = tmp_path / "test.png"
    path.write_bytes(sample_png_bytes)

    document = ImageProcessor().process(path, "doc_5", "test.png")

    assert document.status == DocumentStatus.PENDING_MULTIMODAL_ANALYSIS
    assert document.metadata["width"] == 1920
    assert document.metadata["height"] == 1080
    assert document.metadata["format"] == "PNG"
    assert document.content == []
