import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from image_analyzer.api.images import load_image_row, resolve_file
from image_analyzer.core.db import get_db
from image_analyzer.core.models import CompareResult, ImageInfo
from image_analyzer.pipeline.decode import DecodeError
from image_analyzer.pipeline.hashing import ORIENTATIONS
from image_analyzer.search.compare import Comparison, compare_files
from image_analyzer.search.index import score_rows
from image_analyzer.search.verdict import classify

router = APIRouter(prefix="/api/compare", tags=["compare"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _pair(conn: sqlite3.Connection, a: int, b: int) -> tuple[sqlite3.Row, sqlite3.Row, Comparison]:
    if a == b:
        raise HTTPException(400, "Pick two different images")
    row_a, row_b = load_image_row(conn, a), load_image_row(conn, b)
    if row_a["status"] != "ok" or row_b["status"] != "ok":
        raise HTTPException(409, "Both images must be readable")
    # Only look for a rotation/mirror if the hashes matched the pair that way (or can't say).
    scores = score_rows(row_a, row_b)
    rotated = scores is None or (scores.orientation != 0 and classify(scores) != "different")
    try:
        cmp = compare_files(resolve_file(row_a), row_a["sha256"], resolve_file(row_b), row_b["sha256"],
                            rotated)
    except DecodeError as e:
        raise HTTPException(409, f"Couldn't decode an image: {e}")
    return row_a, row_b, cmp


def _info(row: sqlite3.Row) -> ImageInfo:
    data = dict(row)
    data.pop("root_path", None)
    return ImageInfo(**data)


@router.get("")
def compare(a: int, b: int, conn: Db) -> CompareResult:
    """Every score for a pair: hash distances, embedding cosine, verdict, and pixel-level SSIM."""
    row_a, row_b, cmp = _pair(conn, a, b)
    scores = score_rows(row_a, row_b)
    return CompareResult(
        a=_info(row_a), b=_info(row_b),
        verdict=classify(scores) if scores else None,
        same_sha=row_a["sha256"] == row_b["sha256"],
        phash_distance=scores.phash if scores else None,
        dhash_distance=scores.dhash if scores else None,
        cosine=scores.cosine if scores else None,
        ssim=cmp.ssim, changed_fraction=cmp.changed_fraction,
        width=cmp.width, height=cmp.height,
        aligned_orientation=cmp.orientation,
        aligned_orientation_label=ORIENTATIONS[cmp.orientation][1],
    )


@router.get("/image")
def compare_image(a: int, b: int, kind: Literal["a", "b", "heatmap"], conn: Db) -> Response:
    """The aligned images (same size and orientation) and the difference heatmap."""
    _, _, cmp = _pair(conn, a, b)
    body, media = {"a": (cmp.image_a, "image/jpeg"), "b": (cmp.image_b, "image/jpeg"),
                   "heatmap": (cmp.heatmap, "image/png")}[kind]
    return Response(body, media_type=media, headers={"Cache-Control": "private, max-age=300"})
