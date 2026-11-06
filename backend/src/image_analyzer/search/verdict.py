"""Turn a pair's similarity scores into a verdict: exact, near_duplicate, similar or different.

This is the app's definition of "the same picture". Everything user-facing (match strips,
duplicate groups, the evaluation harness) goes through classify().
"""

from dataclasses import dataclass
from typing import Literal

from image_analyzer.core import thresholds

Level = Literal["exact", "near_duplicate", "similar", "different"]
LEVEL_RANK: dict[Level, int] = {"different": 0, "similar": 1, "near_duplicate": 2, "exact": 3}

# Largest pHash distance the index looks at. Pairs further apart than this are never scored,
# so classify() can't call them near-duplicates whatever its rules say.
CANDIDATE_RADIUS = 20
# Embedding candidates: each image's SEMANTIC_K nearest neighbours, if their cosine is at least
# MIN_COSINE. Like CANDIDATE_RADIUS, these bound what classify() ever gets to see.
SEMANTIC_K = 20
MIN_COSINE = 0.5


@dataclass(frozen=True)
class PairScores:
    same_sha: bool  # byte-identical files
    phash: int  # pHash Hamming distance, 0..64, at the best orientation
    dhash: int  # dHash Hamming distance, 0..64, at that same orientation
    orientation: int  # 0 = as is; 1..7 = rotated and/or mirrored (see hashing.ORIENTATIONS)
    cosine: float | None = None  # embedding similarity, -1..1; None if either image lacks one


def classify(s: PairScores) -> Level:
    """Return the match level for one pair of images. The numbers come from
    core/thresholds.py (defaults 12 / 14 / 0.85), editable on the settings page."""
    t = thresholds.current()
    if s.same_sha:
        return "exact"
    # Near-duplicate rule (Phase 2), chosen from `make eval` on ~/Pictures/sample:
    # catches 97% of edited copies; pHash and dHash must both agree.
    #   if s.phash <= 16 and s.cosine >= 0.90:
    if s.phash <= t.near_phash and s.dhash <= t.near_dhash:
        return "near_duplicate"
    # Similar rule (Phase 3), from `make eval` section 5: cosine >= 0.85 catches ~80% of
    # same-scene pairs (~96% excluding rotated copies) and 57 of 127k unrelated pairs.
    # s.cosine is None when either image has no embedding yet; that falls through to "different".
    if s.cosine is not None and s.cosine >= t.similar_cosine:
        return "similar"
    return "different"
