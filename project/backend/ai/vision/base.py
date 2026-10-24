"""Provider abstraction and controlled errors for visual analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod

from schemas.vision import VisualAnalysis


class VisionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class VisionConfigurationError(VisionError):
    pass


class VisionAuthenticationError(VisionError):
    pass


class VisionRateLimitError(VisionError):
    pass


class VisionTimeoutError(VisionError):
    pass


class VisionConnectionError(VisionError):
    pass


class VisionResponseError(VisionError):
    pass


class VisionClient(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        source_type: str,
        source_location: int,
    ) -> VisualAnalysis:
        raise NotImplementedError
