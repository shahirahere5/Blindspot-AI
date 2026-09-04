"""Image validation and metadata extraction using Pillow.

Images are validated and their metadata is extracted here. Optional visual
understanding is added by services.multimodal_service after normalization.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

import config
from processing.base import BaseProcessor
from processing.exceptions import DocumentProcessingError
from schemas.document import DocumentStatus, FileType, NormalizedDocument


class ImageProcessor(BaseProcessor):
    def process(
        self,
        file_path: Path,
        document_id: str,
        filename: str,
    ) -> NormalizedDocument:
        try:
            with Image.open(file_path) as img:
                img.verify()  # Raises if the image is corrupt/truncated.
        except (UnidentifiedImageError, OSError) as exc:
            raise DocumentProcessingError(f"Invalid or corrupt image: {exc}") from exc

        # Re-open after verify(); verify() leaves the file object unusable
        # for further access, so a fresh handle is required to read metadata.
        try:
            with Image.open(file_path) as img:
                width, height = img.size
                if width * height > max(1, config.VISION_MAX_IMAGE_PIXELS):
                    raise DocumentProcessingError(
                        "Image dimensions exceed the configured safe pixel limit."
                    )
                image_format = img.format or "UNKNOWN"
                mode = img.mode
        except DocumentProcessingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DocumentProcessingError(
                f"Failed to read image metadata: {exc}"
            ) from exc

        return NormalizedDocument(
            document_id=document_id,
            filename=filename,
            file_type=FileType.IMAGE,
            status=DocumentStatus.PENDING_MULTIMODAL_ANALYSIS,
            content=[],
            metadata={
                "width": width,
                "height": height,
                "format": image_format,
                "mode": mode,
            },
            warnings=[
                "Image content requires configured multimodal analysis."
            ],
        )
