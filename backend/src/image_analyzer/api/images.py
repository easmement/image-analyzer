import base64
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from image_analyzer.core.config import settings
from image_analyzer.core.db import get_db
from image_analyzer.core.models import ImageInfo, ImagePage, Match
from image_analyzer.pipeline.hashing import ORIENTATIONS
from image_analyzer.pipeline.process import thumb_path
from image_analyzer.search.index import library_index
from image_analyzer.search.verdict import CANDIDATE_RADIUS, MIN_COSINE, classify

router = APIRouter(prefix="/api/images", tags=["images"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _encode_cursor(rel_path: str, image_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([rel_path, image_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        rel_path, image_id = json.loads(base64.urlsafe_b64decode(cursor))
        return str(rel_path), int(image_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid cursor")


def _load(conn: sqlite3.Connection, image_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT i.*, l.root_path FROM images i JOIN libraries l ON l.id = i.library_id "
        "WHERE i.id = ?",
        (image_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Image {image_id} not found")
    return row


@router.get("")
def list_images(
    conn: Db,
    library_id: int,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 120,
    status: Literal["ok", "error"] | None = None,
) -> ImagePage:
    """Images ordered by path, paged with a keyset cursor (stable while a scan adds rows)."""
    sql = "SELECT * FROM images WHERE library_id = ?"
    params: list = [library_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if cursor:
        sql += " AND (rel_path, id) > (?, ?)"
        params.extend(_decode_cursor(cursor))
    sql += " ORDER BY rel_path, id LIMIT ?"
    params.append(limit + 1)  # one extra row tells us whether there's another page

    rows = conn.execute(sql, params).fetchall()
    items = [ImageInfo(**dict(r)) for r in rows[:limit]]
    next_cursor = _encode_cursor(items[-1].rel_path, items[-1].id) if len(rows) > limit else None
    return ImagePage(items=items, next_cursor=next_cursor)


@router.get("/{image_id}")
def get_image(image_id: int, conn: Db) -> ImageInfo:
    row = dict(_load(conn, image_id))
    row.pop("root_path")
    return ImageInfo(**row)


@router.get("/{image_id}/similar")
def similar_images(
    image_id: int,
    conn: Db,
    method: Literal["perceptual", "semantic"] = "perceptual",
    limit: Annotated[int, Query(ge=1, le=200)] = 24,
    max_distance: Annotated[int, Query(ge=0, le=CANDIDATE_RADIUS)] = CANDIDATE_RADIUS,
    min_cosine: Annotated[float, Query(ge=MIN_COSINE, le=1)] = MIN_COSINE,
) -> list[Match]:
    """Closest images in the same library, each with its verdict: by perceptual hash distance
    (near-duplicates) or by embedding cosine (visually similar), closest first."""
    row = _load(conn, image_id)
    index = library_index(conn, row["library_id"])
    rows = np.flatnonzero(index.f.ids == image_id)
    if not len(rows):
        return []  # unreadable, or not hashed yet (rescan to fill in)
    hits = index.neighbors(int(rows[0]), method=method, radius=max_distance, k=limit,
                           min_cosine=min_cosine)[:limit]
    if not hits:
        return []
    ids = [int(index.f.ids[r]) for r, _ in hits]
    found = conn.execute(f"SELECT * FROM images WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    by_id = {r["id"]: ImageInfo(**dict(r)) for r in found}
    return [
        Match(image=by_id[i], verdict=classify(s), phash_distance=s.phash, dhash_distance=s.dhash,
              orientation=s.orientation, orientation_label=ORIENTATIONS[s.orientation][1],
              cosine=s.cosine)
        for i, (_, s) in zip(ids, hits)
        if i in by_id
    ]


@router.get("/{image_id}/thumbnail", response_class=FileResponse)
def get_thumbnail(image_id: int, conn: Db) -> FileResponse:
    row = _load(conn, image_id)
    path = thumb_path(settings.thumbs_dir, row["sha256"]) if row["sha256"] else None
    if path is None or not path.is_file():
        raise HTTPException(404, "No thumbnail for this image")
    # Thumbnails are named by content hash and the UI requests ?v=<sha256>, so they never change.
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


def load_image_row(conn: sqlite3.Connection, image_id: int) -> sqlite3.Row:
    return _load(conn, image_id)


def resolve_file(row: sqlite3.Row) -> Path:
    """The image's file on disk. rel_path comes from our own scan, but check anyway: never
    reach outside the library."""
    root = Path(row["root_path"]).resolve()
    path = (root / row["rel_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "File not available")
    return path


@router.get("/{image_id}/file", response_class=FileResponse)
def get_file(image_id: int, conn: Db) -> FileResponse:
    return FileResponse(resolve_file(_load(conn, image_id)), headers={"Cache-Control": "no-cache"})
