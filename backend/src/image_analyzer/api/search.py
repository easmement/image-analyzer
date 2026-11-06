import hashlib
import io
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from image_analyzer.core.config import settings
from image_analyzer.core.db import get_db
from image_analyzer.core.models import ImageInfo, Match, SearchResult, UploadInfo
from image_analyzer.pipeline.decode import DecodeError, open_for_features
from image_analyzer.pipeline.embeddings import as_batch, get_extractor, prepare
from image_analyzer.pipeline.hashing import ORIENTATIONS, perceptual_hashes
from image_analyzer.search.index import library_index
from image_analyzer.search.verdict import LEVEL_RANK, classify

router = APIRouter(prefix="/api/search", tags=["search"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/image")
def search_by_image(
    conn: Db,
    file: Annotated[UploadFile, File(description="The image to look for")],
    library_id: Annotated[int | None, Form()] = None,
    limit: Annotated[int, Form(ge=1, le=200)] = 48,
) -> SearchResult:
    """Find matches for an image that isn't in any library. The upload is processed in memory
    and discarded; nothing about it is stored. (Starlette may spool a large upload to a temporary
    file while parsing the request; that file is deleted when the request ends.)"""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image larger than {MAX_UPLOAD_BYTES // 2**20} MB")
    try:
        img, fmt, (width, height) = open_for_features(io.BytesIO(data))  # same path as the scan
    except DecodeError as e:
        raise HTTPException(400, f"Not a readable image: {e}")

    sha = hashlib.sha256(data).hexdigest()
    phash8, dhash8 = perceptual_hashes(img)
    extractor = get_extractor(settings.embedder)
    emb = extractor.embed(as_batch([prepare(img)]))[0] if extractor else None

    library_ids = (
        [library_id] if library_id is not None
        else [r[0] for r in conn.execute("SELECT id FROM libraries")]
    )
    hits = []  # (image id, scores)
    for lib in library_ids:
        index = library_index(conn, lib)
        hits += [(int(index.f.ids[r]), s) for r, s in index.match_external(sha, phash8, dhash8, emb)]
    # Strongest verdict first, then closest by cosine (or pHash when there's no embedding).
    hits.sort(key=lambda h: (-LEVEL_RANK[classify(h[1])], -(h[1].cosine or 0), h[1].phash))
    hits = hits[:limit]

    rows = {}
    if hits:
        ids = [i for i, _ in hits]
        rows = {r["id"]: ImageInfo(**dict(r)) for r in conn.execute(
            f"SELECT * FROM images WHERE id IN ({','.join('?' * len(ids))})", ids)}
    matches = [
        Match(image=rows[i], verdict=classify(s), phash_distance=s.phash, dhash_distance=s.dhash,
              orientation=s.orientation, orientation_label=ORIENTATIONS[s.orientation][1], cosine=s.cosine)
        for i, s in hits if i in rows
    ]
    query = UploadInfo(filename=file.filename, width=width, height=height, format=fmt,
                       sha256=sha, embedded=emb is not None)
    return SearchResult(query=query, matches=matches)
