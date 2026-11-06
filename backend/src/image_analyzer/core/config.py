"""Runtime settings, read from IMAGE_ANALYZER_* environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "image-analyzer"


def _default_workers() -> int:
    # Leave cores for the thread feeding the GPU, the API server and the desktop. Measured on
    # 12 threads (Phase 5): 8 workers ran fastest with embeddings; 10-12 were slower, because
    # extra decoders starve the GPU thread of CPU.
    return max(1, (os.cpu_count() or 2) - 4)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("IMAGE_ANALYZER_DATA_DIR", _default_data_dir())
        ).expanduser()
    )
    host: str = field(default_factory=lambda: os.environ.get("IMAGE_ANALYZER_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("IMAGE_ANALYZER_PORT", "8001")))
    workers: int = field(
        default_factory=lambda: int(os.environ.get("IMAGE_ANALYZER_WORKERS", _default_workers()))
    )
    thumbnail_size: int = 256
    # "dinov2" (default), "fake" (tests: no model download) or "none" (skip embeddings).
    embedder: str = field(default_factory=lambda: os.environ.get("IMAGE_ANALYZER_EMBEDDER", "dinov2"))
    embed_batch: int = field(default_factory=lambda: int(os.environ.get("IMAGE_ANALYZER_EMBED_BATCH", "32")))
    write_batch: int = field(default_factory=lambda: int(os.environ.get("IMAGE_ANALYZER_WRITE_BATCH", "200")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "image-analyzer.db"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"


settings = Settings()
