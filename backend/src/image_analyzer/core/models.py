"""API schemas. These are also the source of the frontend's generated TypeScript types."""

from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["running", "completed", "cancelled", "failed"]


class LibraryCreate(BaseModel):
    path: str
    name: str | None = None


class Library(BaseModel):
    id: int
    root_path: str
    name: str
    created_at: str
    last_scan_at: str | None
    image_count: int
    error_count: int
    total_bytes: int
    watch: bool = False  # rescan automatically when files change
    watch_unavailable: str | None = None  # why watching isn't possible for this folder, if not
    active_job_id: str | None = None  # the running scan, so a reloaded page can resume its progress bar


class LibraryUpdate(BaseModel):
    name: str | None = None
    watch: bool | None = None


class ErrorKind(BaseModel):
    kind: str  # the exception type, e.g. "UnidentifiedImageError"
    count: int
    example: str  # one full message of this kind


class ErrorReport(BaseModel):
    library_id: int
    total: int
    kinds: list[ErrorKind]
    items: list["ImageInfo"]


class ThresholdSettings(BaseModel):
    near_phash: int = Field(ge=0, le=20, description="Near-duplicate: max pHash distance")
    near_dhash: int = Field(ge=0, le=64, description="Near-duplicate: max dHash distance")
    similar_cosine: float = Field(ge=0.5, le=1.0, description="Similar: min embedding cosine")


class AppSettings(BaseModel):
    thresholds: ThresholdSettings
    defaults: ThresholdSettings
    # Read-only: set with IMAGE_ANALYZER_* environment variables, applied on restart.
    config: dict[str, str | int | float | bool | None]


class Job(BaseModel):
    id: str
    kind: str
    library_id: int | None
    status: JobStatus
    total: int
    done: int
    failed: int
    message: str | None = None
    current: str | None = None
    elapsed_s: float | None = None  # wall time so far
    # Seconds spent per stage: walk, model_load, wait (on CPU workers), embed (GPU), write (DB).
    timings: dict[str, float] | None = None


class ImageInfo(BaseModel):
    id: int
    library_id: int
    rel_path: str
    size_bytes: int
    mtime_ns: int
    sha256: str | None
    width: int | None
    height: int | None
    format: str | None
    status: Literal["ok", "error"]
    error: str | None
    indexed_at: str


class ImagePage(BaseModel):
    items: list[ImageInfo]
    next_cursor: str | None


class DuplicateGroup(BaseModel):
    key: str
    level: Literal["exact", "near_duplicate", "similar"]
    count: int
    total_bytes: int
    reclaimable_bytes: int
    best_id: int
    images: list[ImageInfo]


class Match(BaseModel):
    image: ImageInfo
    verdict: Literal["exact", "near_duplicate", "similar", "different"]
    phash_distance: int  # 0..64; lower is closer
    dhash_distance: int
    orientation: int  # 0 = as is; otherwise the match needed a rotation and/or mirror
    orientation_label: str
    cosine: float | None  # embedding similarity, -1..1; None if either image has no embedding


class CompareResult(BaseModel):
    a: ImageInfo
    b: ImageInfo
    verdict: Literal["exact", "near_duplicate", "similar", "different"] | None  # None: not hashed yet
    same_sha: bool
    phash_distance: int | None
    dhash_distance: int | None
    cosine: float | None
    ssim: float  # mean structural similarity after alignment, -1..1
    changed_fraction: float  # share of the frame that visibly differs, 0..1
    width: int  # aligned comparison frame
    height: int
    aligned_orientation: int  # transform applied to B for the pixel comparison
    aligned_orientation_label: str


class UploadInfo(BaseModel):
    filename: str | None
    width: int
    height: int
    format: str
    sha256: str
    embedded: bool  # False if the embedding model isn't available


class SearchResult(BaseModel):
    query: UploadInfo
    matches: list[Match]
