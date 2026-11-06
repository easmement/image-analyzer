import csv
import io
import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from image_analyzer.core.db import get_db
from image_analyzer.core.models import DuplicateGroup
from image_analyzer.search.grouping import exact_groups, near_duplicate_groups, similar_groups

Level = Literal["exact", "near_duplicate", "similar"]

router = APIRouter(prefix="/api/groups", tags=["groups"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("")
def list_groups(conn: Db, library_id: int | None = None, level: Level = "exact") -> list[DuplicateGroup]:
    return _groups(conn, library_id, level)


def _groups(conn: sqlite3.Connection, library_id: int | None, level: Level) -> list[DuplicateGroup]:
    builders = {"exact": exact_groups, "near_duplicate": near_duplicate_groups, "similar": similar_groups}
    return builders[level](conn, library_id)


@router.get("/export")
def export_groups(conn: Db, library_id: int | None = None, level: Level = "exact") -> Response:
    """CSV of every duplicate with its group and whether it's the suggested keeper."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["group", "level", "keep", "library_id", "rel_path", "size_bytes", "sha256"])
    for n, group in enumerate(_groups(conn, library_id, level), start=1):
        for img in group.images:
            writer.writerow([n, group.level, img.id == group.best_id, img.library_id,
                             img.rel_path, img.size_bytes, img.sha256])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="duplicates.csv"'})
