import platform
from functools import cache

from fastapi import APIRouter
from pydantic import BaseModel

from image_analyzer import __version__
from image_analyzer.core.config import settings
from image_analyzer.pipeline.embeddings import extractor_status

router = APIRouter(prefix="/api", tags=["health"])


class TorchInfo(BaseModel):
    version: str
    cuda_available: bool
    device: str | None


class EmbedderInfo(BaseModel):
    configured: str  # dinov2 | fake | none
    name: str | None  # loaded model, once the first scan has loaded it
    device: str | None
    error: str | None


class Health(BaseModel):
    status: str
    version: str
    python: str
    data_dir: str
    torch: TorchInfo
    embedder: EmbedderInfo


@cache
def _torch_info() -> TorchInfo:
    # Importing torch takes a couple of seconds, so do it once, on first request.
    import torch

    cuda = torch.cuda.is_available()
    return TorchInfo(
        version=torch.__version__,
        cuda_available=cuda,
        device=torch.cuda.get_device_name(0) if cuda else None,
    )


@router.get("/health")
def health() -> Health:
    return Health(
        status="ok",
        version=__version__,
        python=platform.python_version(),
        data_dir=str(settings.data_dir),
        torch=_torch_info(),
        embedder=EmbedderInfo(configured=settings.embedder, **extractor_status()),
    )
