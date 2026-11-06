from dataclasses import asdict

from fastapi import APIRouter

from image_analyzer.core import thresholds
from image_analyzer.core.config import settings as config
from image_analyzer.core.models import AppSettings, ThresholdSettings
from image_analyzer.pipeline.embeddings import extractor_status
from image_analyzer.pipeline.process import FEATURES_VERSION
from image_analyzer.search.index import HNSW_THRESHOLD
from image_analyzer.search.verdict import CANDIDATE_RADIUS, MIN_COSINE, SEMANTIC_K

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current() -> AppSettings:
    model = extractor_status()
    return AppSettings(
        thresholds=ThresholdSettings(**asdict(thresholds.current())),
        defaults=ThresholdSettings(**asdict(thresholds.DEFAULTS)),
        config={
            "data_dir": str(config.data_dir),
            "database": str(config.db_path),
            "embedder": config.embedder,
            "model": model["name"],
            "model_device": model["device"],
            "workers": config.workers,
            "embed_batch": config.embed_batch,
            "write_batch": config.write_batch,
            "thumbnail_size": config.thumbnail_size,
            "candidate_radius": CANDIDATE_RADIUS,
            "min_cosine": MIN_COSINE,
            "semantic_k": SEMANTIC_K,
            "hnsw_threshold": HNSW_THRESHOLD,
            "features_version": FEATURES_VERSION,
        },
    )


@router.get("")
def get_settings() -> AppSettings:
    return _current()


@router.put("/thresholds")
def set_thresholds(body: ThresholdSettings) -> AppSettings:
    """Change the verdict thresholds. Takes effect immediately for matches and groups; no rescan
    is needed, because verdicts are computed from stored scores on every request."""
    thresholds.save(thresholds.Thresholds(**body.model_dump()))
    return _current()
