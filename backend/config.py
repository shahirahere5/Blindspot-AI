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
VERSION_GROUPS_DIR = DATA_DIR / "version_groups"
COMPARISON_CACHE_DIR = DATA_DIR / "comparison_cache"
GRAPH_STORE_DIR = DATA_DIR / "knowledge_graph"

# Ensure storage directories exist at import time.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
VERSION_GROUPS_DIR.mkdir(parents=True, exist_ok=True)
COMPARISON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
GRAPH_STORE_DIR.mkdir(parents=True, exist_ok=True)

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


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable (1/true/yes/on, case-insensitive)."""
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Read a comma-separated environment variable as trimmed values."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


# Browser origins permitted to call the API directly. The defaults are the
# two loopback forms used by Vite in development; deployments should set this
# to their exact frontend origin(s). An empty value disables cross-origin use.
FRONTEND_ORIGINS = _env_csv(
    "FRONTEND_ORIGINS",
    ("http://localhost:5173", "http://127.0.0.1:5173"),
)


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

# ---------------------------------------------------------------------------
# Phase 3: multi-agent debate engine configuration
# ---------------------------------------------------------------------------
# The six specialist agents run concurrently, but concurrency is bounded by
# a semaphore rather than left uncontrolled, out of consideration for
# free-tier Groq rate limits. Defaults to running all six at once (there are
# only six), but can be lowered via the environment if rate limiting becomes
# an issue on a given Groq account.
DEBATE_MAX_CONCURRENT_AGENTS = _env_int("DEBATE_MAX_CONCURRENT_AGENTS", 6)

# ---------------------------------------------------------------------------
# Phase 4: Retrieval-Augmented Generation (RAG) configuration
# ---------------------------------------------------------------------------
# RAG is opt-in and defaults to OFF so Phase 1-3 behavior (and every
# Phase 1-3 test) is completely unaffected unless a deployment explicitly
# enables it. When disabled, /analyze and /debate build their prompts
# exactly as before (the full labeled document content, unchanged).
RAG_ENABLED = _env_bool("RAG_ENABLED", False)

# Chunking: character-based chunk size and overlap. Chunking is word-aware
# (never splits mid-word) but these limits are expressed in characters,
# since that's what MAX_ANALYSIS_CONTENT_CHARS is already expressed in.
RAG_CHUNK_SIZE = _env_int("RAG_CHUNK_SIZE", 800)
RAG_CHUNK_OVERLAP = _env_int("RAG_CHUNK_OVERLAP", 150)

# Retrieval: how many chunks to retrieve per query by default.
RAG_TOP_K = _env_int("RAG_TOP_K", 5)

# Phase 8 comparisons use a separately bounded retrieval budget. Retrieval
# is always performed once per explicitly selected document, preserving the
# per-document isolation guarantees of the vector store.
COMPARISON_RAG_TOP_K = _env_int("COMPARISON_RAG_TOP_K", 8)
MAX_COMPARISON_CONTENT_CHARS = _env_int(
    "MAX_COMPARISON_CONTENT_CHARS", 30_000
)

# Phase 9 graph responses and neighbor traversal are deliberately bounded.
# The graph extends structured analysis; it never replaces RAG retrieval.
GRAPH_MAX_NODES = max(10, _env_int("GRAPH_MAX_NODES", 300))
GRAPH_MAX_EDGES = max(10, _env_int("GRAPH_MAX_EDGES", 600))
GRAPH_MAX_TRAVERSAL_DEPTH = max(1, min(5, _env_int("GRAPH_MAX_TRAVERSAL_DEPTH", 2)))

# Embedding provider. "hashing" is the only provider implemented today: a
# free, fully local, dependency-free, deterministic feature-hashing
# embedding (see ai/embeddings/hashing.py for why this was chosen over
# requiring a paid embedding API or a heavy local model download). The
# interface (ai/embeddings/base.py) is provider-independent so a real
# semantic embedding model can be dropped in later without touching any
# other Phase 4 code.
RAG_EMBEDDING_PROVIDER = _env_str("RAG_EMBEDDING_PROVIDER", "hashing")

# Vector dimensionality used by the hashing embedding provider. Only
# relevant when RAG_EMBEDDING_PROVIDER=hashing.
RAG_EMBEDDING_DIMENSION = _env_int("RAG_EMBEDDING_DIMENSION", 256)

# Where the local vector store persists its per-document index files
# between application restarts.
RAG_VECTOR_STORE_PATH = Path(
    _env_str("RAG_VECTOR_STORE_PATH", str(DATA_DIR / "vector_store"))
)
RAG_VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Optional multimodal document processing
# ---------------------------------------------------------------------------
# Disabled by default so existing text-first uploads never make extra provider
# calls. The OpenAI-compatible client can use Groq or another compatible
# endpoint without changing the configured text model.
MULTIMODAL_ENABLED = _env_bool("MULTIMODAL_ENABLED", False)
VISION_PROVIDER = _env_str("VISION_PROVIDER", "groq")
VISION_API_KEY = os.environ.get("VISION_API_KEY") or ""
VISION_MODEL = os.environ.get("VISION_MODEL") or ""
VISION_BASE_URL = os.environ.get("VISION_BASE_URL") or ""
VISION_TIMEOUT_SECONDS = _env_float("VISION_TIMEOUT_SECONDS", 60.0)
VISION_DOCUMENT_TIMEOUT_SECONDS = _env_float(
    "VISION_DOCUMENT_TIMEOUT_SECONDS", 150.0
)
VISION_CONNECT_TIMEOUT_SECONDS = _env_float(
    "VISION_CONNECT_TIMEOUT_SECONDS", 5.0
)

# Resource controls: visual candidates are processed sequentially, capped per
# document, and downscaled before transport when a rendered PDF page would be
# excessively large.
VISION_MAX_ITEMS_PER_DOCUMENT = _env_int("VISION_MAX_ITEMS_PER_DOCUMENT", 10)
VISION_MAX_IMAGE_PIXELS = _env_int("VISION_MAX_IMAGE_PIXELS", 20_000_000)
VISION_PDF_RENDER_SCALE = _env_float("VISION_PDF_RENDER_SCALE", 1.5)
VISION_MIN_TEXT_CHARS_PER_PAGE = _env_int(
    "VISION_MIN_TEXT_CHARS_PER_PAGE", 20
)
VISION_MIN_IMAGE_COVERAGE = _env_float("VISION_MIN_IMAGE_COVERAGE", 0.15)
VISION_MIN_EMBEDDED_IMAGE_WIDTH = _env_int(
    "VISION_MIN_EMBEDDED_IMAGE_WIDTH", 200
)
VISION_MIN_EMBEDDED_IMAGE_HEIGHT = _env_int(
    "VISION_MIN_EMBEDDED_IMAGE_HEIGHT", 120
)
