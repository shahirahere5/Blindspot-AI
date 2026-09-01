"""
Centralized configuration for Blind Spot AI.

All tunable settings (paths, size limits, allowed types, AI provider
settings) live here so that nothing is hardcoded across the rest of the
application. Phase 2 settings are read from environment variables so no
secrets or environment-specific values are hardcoded.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional; if it's not installed, environment
    # variables can still be set directly in the shell/OS.
    pass

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DOCUMENTS_DIR = DATA_DIR / "documents"

# Ensure storage directories exist at import time.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Upload constraints
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB, per hackathon MVP requirement

# Maps a normalized "file_type" to the set of accepted file extensions.
SUPPORTED_EXTENSIONS = {
    "pdf": {".pdf"},
    "pptx": {".pptx"},
    "docx": {".docx"},
    "txt": {".txt"},
    "image": {".png", ".jpg", ".jpeg", ".webp"},
}

# Maps a normalized "file_type" to acceptable MIME types (best-effort check;
# browsers/clients are not always consistent about MIME types, so this is
# used as a soft signal rather than the sole source of truth).
SUPPORTED_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "txt": {"text/plain"},
    "image": {"image/png", "image/jpeg", "image/webp"},
}

ALL_ALLOWED_EXTENSIONS = {
    ext for exts in SUPPORTED_EXTENSIONS.values() for ext in exts
}


def extension_to_file_type(extension: str) -> str | None:
    """Return the normalized file_type for a given extension, or None."""
    extension = extension.lower()
    for file_type, extensions in SUPPORTED_EXTENSIONS.items():
        if extension in extensions:
            return file_type
    return None


def _env_str(name: str, default: str) -> str:
    """Read a string environment variable, treating blank/whitespace-only
    values the same as unset so a blank line in `.env` still falls back to
    the default instead of silently becoming an empty string."""
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to a default."""
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to a default."""
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Phase 2: AI analysis configuration
# ---------------------------------------------------------------------------
# All of these are read at import time from environment variables so nothing
# provider-specific (and no secrets) are hardcoded. See `.env.example`.

# Which AI provider/client implementation to use. Only "groq" is implemented
# today, but this makes swapping providers later trivial.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "groq")

# --- Groq connection settings -----------------------------------------------
# Groq exposes an OpenAI-compatible Chat Completions API. No default is
# provided for the API key -- it must be explicitly set, and its absence is
# treated as a configuration error rather than silently falling back.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or ""
GROQ_MODEL = _env_str("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = _env_str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_TIMEOUT_SECONDS = _env_float("GROQ_TIMEOUT_SECONDS", 60.0)
GROQ_CONNECT_TIMEOUT_SECONDS = _env_float("GROQ_CONNECT_TIMEOUT_SECONDS", 5.0)

# Model sampling settings (kept low/deterministic for structured JSON output).
GROQ_TEMPERATURE = _env_float("GROQ_TEMPERATURE", 0.2)

# Maximum number of characters of document content sent to the model in a
# single analysis pass. This is a simple, configurable safeguard against
# unbounded context for large documents (no chunking/RAG in Phase 2).
MAX_ANALYSIS_CONTENT_CHARS = _env_int("MAX_ANALYSIS_CONTENT_CHARS", 20_000)
