"""Custom exceptions for the document processing layer."""


class DocumentProcessingError(Exception):
    """Raised when a file cannot be processed (e.g. corrupt file)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnsupportedFileTypeError(Exception):
    """Raised when a file extension/type is not supported."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EmptyFileError(Exception):
    """Raised when the uploaded file has no content."""

    def __init__(self, message: str = "Uploaded file is empty.") -> None:
        self.message = message
        super().__init__(message)


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds the configured size limit."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
