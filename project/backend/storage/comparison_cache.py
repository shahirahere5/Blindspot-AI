"""Small atomic cache for immutable version comparison results."""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from pathlib import Path

from config import COMPARISON_CACHE_DIR
from schemas.comparison import ComparisonReport


class ComparisonCacheError(Exception):
    pass


class ComparisonCache:
    def __init__(self, cache_dir: Path = COMPARISON_CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, old_id: str, new_id: str, model: str) -> Path:
        digest = hashlib.sha256(f"{old_id}\0{new_id}\0{model}".encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def load(self, old_id: str, new_id: str, model: str) -> ComparisonReport | None:
        path = self._path(old_id, new_id, model)
        with self._lock:
            if not path.exists():
                return None
            try:
                return ComparisonReport.model_validate_json(path.read_text("utf-8"))
            except Exception as exc:
                raise ComparisonCacheError("Stored comparison is invalid.") from exc

    def save(self, report: ComparisonReport, model: str) -> None:
        path = self._path(report.old_document_id, report.new_document_id, model)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        with self._lock:
            try:
                temporary.write_text(report.model_dump_json(indent=2), encoding="utf-8")
                os.replace(temporary, path)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise ComparisonCacheError("Failed to cache comparison.") from exc


comparison_cache = ComparisonCache()
