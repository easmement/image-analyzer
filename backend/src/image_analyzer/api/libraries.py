import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from image_analyzer.core.db import get_db
from image_analyzer.core.models import ErrorKind, ErrorReport, ImageInfo, Job, Library, LibraryCreate, LibraryUpdate
from image_analyzer.jobs.runner import JobConflict, jobs
from image_analyzer.jobs.watcher import can_watch, watcher

router = APIRouter(prefix="/api/libraries", tags=["libraries"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]

LIBRARY_SELECT = """
SELECT l.id, l.root_path, l.name, l.created_at, l.last_scan_at, l.watch,
       COUNT(i.id) AS image_count,
       COALESCE(SUM(i.status = 'error'), 0) AS error_count,
       COALESCE(SUM(i.size_bytes), 0) AS total_bytes
FROM libraries l LEFT JOIN images i ON i.library_id = l.id
"""


def _library(row: sqlite3.Row) -> Library:
    running = jobs.running_for(row["id"])
    return Library(**dict(row), active_job_id=running.id if running else None,
                   watch_unavailable=can_watch(Path(row["root_path"])))


def load_library(conn: sqlite3.Connection, library_id: int) -> Library:
    row = conn.execute(f"{LIBRARY_SELECT} WHERE l.id = ? GROUP BY l.id", (library_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Library {library_id} not found")
    return _library(row)


@router.get("")
def list_libraries(conn: Db) -> list[Library]:
    rows = conn.execute(f"{LIBRARY_SELECT} GROUP BY l.id ORDER BY l.name").fetchall()
    return [_library(r) for r in rows]


@router.post("", status_code=201)
def create_library(body: LibraryCreate, conn: Db) -> Library:
    path = Path(body.path).expanduser()
    if not path.is_absolute():
        raise HTTPException(400, "Path must be absolute")
    try:
        root = path.resolve(strict=True)
    except OSError:
        raise HTTPException(400, f"Folder not found: {path}")
    if not root.is_dir():
        raise HTTPException(400, f"Not a folder: {root}")
    try:
        cur = conn.execute(
            "INSERT INTO libraries (root_path, name) VALUES (?, ?)",
            (str(root), body.name or root.name or str(root)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Library already registered: {root}")
    return load_library(conn, cur.lastrowid)  # type: ignore[arg-type]


@router.get("/{library_id}")
def get_library(library_id: int, conn: Db) -> Library:
    return load_library(conn, library_id)


@router.patch("/{library_id}")
def update_library(library_id: int, body: LibraryUpdate, conn: Db) -> Library:
    """Rename a library, or turn watch mode (automatic rescans on file changes) on or off."""
    library = load_library(conn, library_id)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "Name can't be empty")
        conn.execute("UPDATE libraries SET name = ? WHERE id = ?", (body.name.strip(), library_id))
    if body.watch is not None:
        root = Path(library.root_path)
        if body.watch and (reason := can_watch(root)):
            raise HTTPException(400, reason)
        conn.execute("UPDATE libraries SET watch = ? WHERE id = ?", (int(body.watch), library_id))
        if body.watch:
            watcher.watch(library_id, root)
        else:
            watcher.unwatch(library_id)
    conn.commit()
    return load_library(conn, library_id)


@router.delete("/{library_id}", status_code=204)
def delete_library(library_id: int, conn: Db) -> None:
    """Forget a library and its index. Never touches the image files."""
    load_library(conn, library_id)
    if jobs.running_for(library_id):
        raise HTTPException(409, "A scan is running for this library; cancel it first")
    watcher.unwatch(library_id)
    conn.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
    conn.commit()


@router.get("/{library_id}/errors")
def library_errors(library_id: int, conn: Db) -> ErrorReport:
    """Files that couldn't be read, grouped by the kind of error."""
    load_library(conn, library_id)
    rows = conn.execute(
        "SELECT * FROM images WHERE library_id = ? AND status = 'error' ORDER BY rel_path", (library_id,)
    ).fetchall()
    items = [ImageInfo(**dict(r)) for r in rows]
    kinds: dict[str, ErrorKind] = {}
    for img in items:
        kind = (img.error or "Unknown").split(":", 1)[0]
        if kind in kinds:
            kinds[kind].count += 1
        else:
            kinds[kind] = ErrorKind(kind=kind, count=1, example=img.error or "")
    return ErrorReport(library_id=library_id, total=len(items),
                       kinds=sorted(kinds.values(), key=lambda k: -k.count), items=items)


@router.post("/{library_id}/scan", status_code=202)
def start_scan(library_id: int, conn: Db, full: bool = False, retry_errors: bool = False) -> Job:
    """Incremental scan. full: reprocess everything. retry_errors: also retry unreadable files."""
    library = load_library(conn, library_id)
    root = Path(library.root_path)
    if not root.is_dir():
        raise HTTPException(409, f"Library folder is missing: {root}")
    try:
        return jobs.start_scan(library_id, root, full=full, retry_errors=retry_errors).snapshot()
    except JobConflict as e:
        raise HTTPException(409, f"Scan already running: job {e}")
