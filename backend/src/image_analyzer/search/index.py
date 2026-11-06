"""Per-library search over perceptual hashes (near-duplicates) and embeddings (similar images).

Candidate pairs come from either index:
  - pHash: every pair within CANDIDATE_RADIUS, orientation-aware (see best_orientation);
  - embeddings: each image's SEMANTIC_K nearest neighbours by cosine, if >= MIN_COSINE.
Every candidate is then scored on both, so classify() always sees the full picture.
"""

import sqlite3
import threading
from dataclasses import dataclass
from typing import Literal

import faiss
import numpy as np

from image_analyzer.pipeline.hashing import HASH_BYTES, N_ORIENTATIONS, as_codes, hamming
from image_analyzer.search.verdict import CANDIDATE_RADIUS, MIN_COSINE, SEMANTIC_K, PairScores

# Above this many embeddings, an exact (flat) search per query gets slow: switch to HNSW, an
# approximate graph index (~99% recall at efSearch=64, much faster per query; build takes longer).
HNSW_THRESHOLD = 500_000
HNSW_M = 32
HNSW_EF_SEARCH = 64


@dataclass
class FeatureSet:
    ids: np.ndarray  # (n,) image ids
    sha: list[str]
    phash: np.ndarray  # (n, 8, 8) uint8: image, orientation, hash bytes
    dhash: np.ndarray
    emb: np.ndarray | None = None  # (n, dim) float32, L2-normalised; zero rows where missing
    has_emb: np.ndarray | None = None  # (n,) bool

    def __len__(self) -> int:
        return len(self.ids)


def best_orientation(pa, pb, da, db) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scores for pairs (a, b) given their (..., 8, 8) hash arrays. Returns arrays of
    (phash distance, dhash distance, orientation), picking the orientation with the smallest
    pHash distance (dHash breaks ties), over a's orientations vs b and b's vs a."""
    p = np.concatenate([hamming(pa, pb[..., None, 0, :]), hamming(pb, pa[..., None, 0, :])], axis=-1)
    d = np.concatenate([hamming(da, db[..., None, 0, :]), hamming(db, da[..., None, 0, :])], axis=-1)
    best = np.argmin(p * 65 + d, axis=-1)[..., None]
    return (np.take_along_axis(p, best, -1)[..., 0], np.take_along_axis(d, best, -1)[..., 0],
            best[..., 0] % N_ORIENTATIONS)


class LibraryIndex:
    def __init__(self, features: FeatureSet):
        self.f = features
        self.hash_index = faiss.IndexBinaryFlat(HASH_BYTES * 8)
        if len(features):
            self.hash_index.add(np.ascontiguousarray(features.phash[:, 0, :]))
        self.emb_index = None
        self.emb_rows = np.empty(0, dtype=np.int64)  # emb_index position -> feature row
        if features.emb is not None and features.has_emb is not None and features.has_emb.any():
            self.emb_rows = np.flatnonzero(features.has_emb)
            dim = features.emb.shape[1]
            if len(self.emb_rows) > HNSW_THRESHOLD:
                self.emb_index = faiss.IndexHNSWFlat(dim, HNSW_M, faiss.METRIC_INNER_PRODUCT)
                self.emb_index.hnsw.efSearch = HNSW_EF_SEARCH
            else:
                self.emb_index = faiss.IndexFlatIP(dim)  # exact; inner product = cosine here
            self.emb_index.add(np.ascontiguousarray(features.emb[self.emb_rows]))

    # --- scoring --------------------------------------------------------------------------

    def scores(self, i: np.ndarray, j: np.ndarray) -> list[PairScores]:
        f = self.f
        p, d, o = best_orientation(f.phash[i], f.phash[j], f.dhash[i], f.dhash[j])
        if f.emb is not None and f.has_emb is not None:
            cos = np.einsum("nd,nd->n", f.emb[i], f.emb[j])
            both = f.has_emb[i] & f.has_emb[j]
        else:
            cos, both = np.zeros(len(i)), np.zeros(len(i), dtype=bool)
        return [
            PairScores(same_sha=f.sha[a] == f.sha[b], phash=int(pp), dhash=int(dd), orientation=int(oo),
                       cosine=round(float(c), 4) if ok else None)
            for a, b, pp, dd, oo, c, ok in zip(i, j, p, d, o, cos, both)
        ]

    # --- candidates -----------------------------------------------------------------------

    def _hash_candidates(self, radius: int) -> np.ndarray:
        queries = self.f.phash.reshape(-1, HASH_BYTES)  # every orientation of every image
        lims, _, found = self.hash_index.range_search(queries, radius + 1)  # FAISS radius is exclusive
        # lims is uint64; mixing it with int64 indices would promote to float64.
        rows = np.repeat(np.arange(len(queries), dtype=np.int64), np.diff(lims.astype(np.int64)))
        return np.stack([rows // N_ORIENTATIONS, found.astype(np.int64)], axis=1)

    def _emb_candidates(self, k: int, min_cosine: float) -> np.ndarray:
        emb = self.f.emb
        if self.emb_index is None or emb is None:
            return np.empty((0, 2), dtype=np.int64)
        k = min(k + 1, len(self.emb_rows))  # +1: each image finds itself first
        sims, found = self.emb_index.search(np.ascontiguousarray(emb[self.emb_rows]), k)
        query = np.repeat(self.emb_rows, k)
        keep = (sims.reshape(-1) >= min_cosine) & (found.reshape(-1) >= 0)
        return np.stack([query[keep], self.emb_rows[found.reshape(-1)[keep]]], axis=1)

    def pairs(self, radius: int = CANDIDATE_RADIUS, k: int = SEMANTIC_K,
              min_cosine: float = MIN_COSINE) -> list[tuple[int, int, PairScores]]:
        """Every candidate pair of rows (i < j), with scores."""
        n = len(self.f)
        if n < 2:
            return []
        cand = np.concatenate([self._hash_candidates(radius), self._emb_candidates(k, min_cosine)])
        a, b = cand.min(axis=1), cand.max(axis=1)
        keys = np.unique((a * n + b)[a != b])
        i, j = keys // n, keys % n
        return [
            (int(x), int(y), s) for x, y, s in zip(i, j, self.scores(i, j))
            if s.phash <= radius or (s.cosine is not None and s.cosine >= min_cosine)
        ]

    def neighbors(self, row: int, method: Literal["perceptual", "semantic"] = "perceptual",
                  radius: int = CANDIDATE_RADIUS, k: int = SEMANTIC_K,
                  min_cosine: float = MIN_COSINE) -> list[tuple[int, PairScores]]:
        """Closest rows to one row: by pHash (perceptual) or by embedding cosine (semantic)."""
        if method == "semantic":
            emb, has_emb = self.f.emb, self.f.has_emb
            if self.emb_index is None or emb is None or has_emb is None or not has_emb[row]:
                return []
            k = min(k + 1, len(self.emb_rows))
            sims, found = self.emb_index.search(emb[row : row + 1], k)
            others = np.array([self.emb_rows[x] for x, s in zip(found[0], sims[0])
                               if x >= 0 and s >= min_cosine and self.emb_rows[x] != row], dtype=np.int64)
            hits = list(zip(others.tolist(), self.scores(np.full(len(others), row), others)))
            return sorted(hits, key=lambda h: -(h[1].cosine or 0))
        others = np.array([r for r in range(len(self.f)) if r != row], dtype=np.int64)
        if not len(others):
            return []
        hits = [(int(r), s) for r, s in zip(others, self.scores(np.full(len(others), row), others))
                if s.phash <= radius]
        return sorted(hits, key=lambda h: (h[1].phash, h[1].dhash))


    def match_external(self, sha: str, phash8: bytes, dhash8: bytes, emb: np.ndarray | None,
                       radius: int = CANDIDATE_RADIUS, min_cosine: float = MIN_COSINE
                       ) -> list[tuple[int, PairScores]]:
        """Score an image that isn't in the library (an upload) against every row."""
        n = len(self.f)
        if not n:
            return []
        p, d = as_codes([phash8])[0], as_codes([dhash8])[0]
        pd, dd, o = best_orientation(np.broadcast_to(p, (n, *p.shape)), self.f.phash,
                                     np.broadcast_to(d, (n, *d.shape)), self.f.dhash)
        if emb is not None and self.f.emb is not None and self.f.has_emb is not None:
            cos = self.f.emb @ emb.astype(np.float32)
            has = self.f.has_emb
        else:
            cos, has = np.zeros(n), np.zeros(n, dtype=bool)
        hits = []
        for r in range(n):
            c = round(float(cos[r]), 4) if has[r] else None
            if pd[r] <= radius or (c is not None and c >= min_cosine):
                hits.append((r, PairScores(same_sha=self.f.sha[r] == sha, phash=int(pd[r]),
                                           dhash=int(dd[r]), orientation=int(o[r]), cosine=c)))
        return hits


def score_rows(a: sqlite3.Row, b: sqlite3.Row) -> PairScores | None:
    """Scores for two stored images, possibly from different libraries. None if either hasn't
    been hashed yet."""
    if not (a["phash8"] and b["phash8"]):
        return None
    p, d = as_codes([a["phash8"], b["phash8"]]), as_codes([a["dhash8"], b["dhash8"]])
    pd, dd, o = best_orientation(p[:1], p[1:], d[:1], d[1:])
    cosine = None
    if a["embedding"] and b["embedding"] and len(a["embedding"]) == len(b["embedding"]):
        va = np.frombuffer(a["embedding"], dtype=np.float16).astype(np.float32)
        vb = np.frombuffer(b["embedding"], dtype=np.float16).astype(np.float32)
        cosine = round(float(va @ vb), 4)
    return PairScores(same_sha=a["sha256"] == b["sha256"], phash=int(pd[0]), dhash=int(dd[0]),
                      orientation=int(o[0]), cosine=cosine)


# --- per-library cache --------------------------------------------------------------------

_cache: dict[int, tuple[tuple, LibraryIndex]] = {}
_cache_lock = threading.Lock()


def load_features(conn: sqlite3.Connection, library_id: int) -> FeatureSet:
    rows = conn.execute(
        "SELECT id, sha256, phash8, dhash8, embedding FROM images "
        "WHERE library_id = ? AND status = 'ok' AND phash8 IS NOT NULL ORDER BY id",
        (library_id,),
    ).fetchall()
    embs = [np.frombuffer(r["embedding"], dtype=np.float16) if r["embedding"] else None for r in rows]
    dim = next((len(e) for e in embs if e is not None), 0)
    emb = np.zeros((len(rows), dim), dtype=np.float32)
    has_emb = np.zeros(len(rows), dtype=bool)
    for n, e in enumerate(embs):
        if e is not None and len(e) == dim:
            emb[n], has_emb[n] = e, True
    return FeatureSet(
        ids=np.array([r["id"] for r in rows], dtype=np.int64),
        sha=[r["sha256"] for r in rows],
        phash=as_codes([r["phash8"] for r in rows]),
        dhash=as_codes([r["dhash8"] for r in rows]),
        emb=emb if dim else None,
        has_emb=has_emb if dim else None,
    )


def library_index(conn: sqlite3.Connection, library_id: int) -> LibraryIndex:
    """The library's index, rebuilt whenever its rows change (any scan, even a cancelled one)."""
    version = tuple(conn.execute(
        "SELECT COUNT(*), MAX(indexed_at), MAX(id) FROM images WHERE library_id = ?", (library_id,)
    ).fetchone())
    with _cache_lock:
        cached = _cache.get(library_id)
        if cached and cached[0] == version:
            return cached[1]
    index = LibraryIndex(load_features(conn, library_id))
    with _cache_lock:
        _cache[library_id] = (version, index)
    return index
