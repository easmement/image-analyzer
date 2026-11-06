"""Duplicate groups: exact (same SHA-256), plus near-duplicate and similar groups built by joining
candidate pairs (from the hash and embedding indexes) with union-find."""

import re
import sqlite3
from pathlib import PurePosixPath
from typing import Literal

from image_analyzer.core.models import DuplicateGroup, ImageInfo
from image_analyzer.search.index import library_index
from image_analyzer.search.verdict import LEVEL_RANK, classify

# Camera originals: IMG_0012.jpg. Copies tend to gain suffixes: "IMG_0012 (1).jpg",
# "IMG_0012-copy.jpg", "Copy of IMG_0012.jpg".
CAMERA_NAME = re.compile(r"^IMG_\d{4}\.jpe?g$", re.IGNORECASE)


def pick_best(images: list[ImageInfo]) -> int:
    """Return the id of the copy to keep from a group of duplicates. The UI highlights it, and
    reclaimable_bytes counts everything else in the group.

    Every image here is status "ok". Quality comes first (pixels, then file size); for exact
    duplicates those always tie, so the name, folder depth and file age decide.
    """
    return min(
        images,
        key=lambda i: (
            -(i.width or 0) * (i.height or 0),                  # 1. most pixels (Phase 2+; ties for exact dups)
            -i.size_bytes,                                      # 2. least compressed at that resolution
            not CAMERA_NAME.match(PurePosixPath(i.rel_path).name),  # 3. untouched camera name wins
            i.rel_path.count("/"),                              # 4. shallowest folder
            i.mtime_ns,                                         # 5. oldest file (weak: copies reset it)
            i.rel_path,                                         # 6. deterministic final tie-break
        ),
    ).id


def exact_groups(conn: sqlite3.Connection, library_id: int | None = None) -> list[DuplicateGroup]:
    where, params = ("AND library_id = ?", (library_id,)) if library_id is not None else ("", ())
    rows = conn.execute(
        f"""
        SELECT * FROM images
        WHERE status = 'ok' {where} AND sha256 IN (
            SELECT sha256 FROM images WHERE status = 'ok' {where}
            GROUP BY sha256 HAVING COUNT(*) > 1
        )
        ORDER BY sha256, rel_path
        """,
        params * 2,
    ).fetchall()

    by_sha: dict[str, list[ImageInfo]] = {}
    for r in rows:
        by_sha.setdefault(r["sha256"], []).append(ImageInfo(**dict(r)))
    return _sorted([_group("exact", sha, images) for sha, images in by_sha.items()])


def near_duplicate_groups(conn: sqlite3.Connection, library_id: int | None = None) -> list[DuplicateGroup]:
    return linked_groups(conn, "near_duplicate", library_id)


def similar_groups(conn: sqlite3.Connection, library_id: int | None = None) -> list[DuplicateGroup]:
    return linked_groups(conn, "similar", library_id)


def linked_groups(
    conn: sqlite3.Connection, level: Literal["near_duplicate", "similar"], library_id: int | None = None
) -> list[DuplicateGroup]:
    """Connected components of pairs classified `level` or better (so similar includes
    near-duplicate and exact pairs)."""
    library_ids = (
        [library_id] if library_id is not None
        else [r[0] for r in conn.execute("SELECT id FROM libraries")]
    )
    groups = []
    for lib in library_ids:
        index = library_index(conn, lib)
        parent = list(range(len(index.f)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path halving keeps the trees shallow
                x = parent[x]
            return x

        for i, j, scores in index.pairs():
            if LEVEL_RANK[classify(scores)] >= LEVEL_RANK[level]:
                parent[find(i)] = find(j)

        components: dict[int, list[int]] = {}
        for row in range(len(parent)):
            components.setdefault(find(row), []).append(int(index.f.ids[row]))
        members = [ids for ids in components.values() if len(ids) > 1]
        if not members:
            continue
        rows = conn.execute(
            f"SELECT * FROM images WHERE id IN ({','.join('?' * sum(map(len, members)))})",
            [i for ids in members for i in ids],
        ).fetchall()
        by_id = {r["id"]: ImageInfo(**dict(r)) for r in rows}
        for ids in members:
            images = sorted((by_id[i] for i in ids), key=lambda im: im.rel_path)
            groups.append(_group(level, f"{level}-{min(ids)}", images))
    return _sorted(groups)


def _group(level: Literal["exact", "near_duplicate", "similar"], key: str, images: list[ImageInfo]) -> DuplicateGroup:
    best = pick_best(images)
    total = sum(i.size_bytes for i in images)
    keep = next(i.size_bytes for i in images if i.id == best)
    return DuplicateGroup(key=key, level=level, count=len(images), total_bytes=total,
                          reclaimable_bytes=total - keep, best_id=best, images=images)


def _sorted(groups: list[DuplicateGroup]) -> list[DuplicateGroup]:
    return sorted(groups, key=lambda g: (-g.reclaimable_bytes, -g.count))
