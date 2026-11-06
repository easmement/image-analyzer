from pathlib import Path

import numpy as np
from PIL import Image

from image_analyzer.devtools.make_fixtures import build, synthetic_sources
from image_analyzer.pipeline.decode import open_for_features
from image_analyzer.pipeline.embeddings import FakeExtractor, as_batch, prepare
from image_analyzer.pipeline.hashing import as_codes, perceptual_hashes
from image_analyzer.search.index import FeatureSet, LibraryIndex


def _features(paths: list[Path]) -> FeatureSet:
    hashes = [perceptual_hashes(open_for_features(p)[0]) for p in paths]
    return FeatureSet(
        ids=np.arange(len(paths)), sha=[str(p) for p in paths],
        phash=as_codes([h[0] for h in hashes]), dhash=as_codes([h[1] for h in hashes]),
    )


def test_orientation_0_is_the_plain_image():
    img = Image.effect_mandelbrot((256, 192), (-2, -1.2, 1, 1.2), 64).convert("RGB")
    phash8, _ = perceptual_hashes(img)
    rotated8, _ = perceptual_hashes(img.transpose(Image.Transpose.ROTATE_90))
    # Hashing the rotated image as-is gives the original's "rotated 90°" entry.
    assert rotated8[:8] == phash8[8:16]


def test_rotated_and_mirrored_copies_match_their_original(tmp_path):
    sources = synthetic_sources(3, tmp_path / "src")
    build(sources, tmp_path / "out")
    group = tmp_path / "out" / "images" / sources[0].stem
    names = ["original.jpg", "rot90.jpg", "mirror.jpg", "exif_rotated.jpg"]
    index = LibraryIndex(_features([group / n for n in names]))
    by_name = {names[r]: s for r, s in index.neighbors(0)}
    assert by_name["rot90.jpg"].phash <= 4 and by_name["rot90.jpg"].orientation != 0
    assert by_name["mirror.jpg"].phash <= 4 and by_name["mirror.jpg"].orientation != 0
    # EXIF orientation is applied at decode time, so this one needs no rotation to match.
    assert by_name["exif_rotated.jpg"].phash <= 4 and by_name["exif_rotated.jpg"].orientation == 0


def test_pairs_are_symmetric_and_unique(tmp_path):
    sources = synthetic_sources(2, tmp_path / "src")
    build(sources, tmp_path / "out")
    paths = sorted((tmp_path / "out" / "images").rglob("*.*"))
    index = LibraryIndex(_features(paths))
    pairs = index.pairs(radius=64)
    keys = [(i, j) for i, j, _ in pairs]
    assert len(keys) == len(set(keys)) == len(paths) * (len(paths) - 1) // 2
    assert all(i < j for i, j in keys)
    # neighbors() and pairs() agree on scores
    from_pairs = {j: s for i, j, s in pairs if i == 0}
    from_neighbors = dict(index.neighbors(0, radius=64))
    assert from_pairs == from_neighbors


def _with_embeddings(paths: list[Path]) -> FeatureSet:
    f = _features(paths)
    batch = as_batch([prepare(open_for_features(p)[0]) for p in paths])
    f.emb = FakeExtractor().embed(batch)
    f.has_emb = np.ones(len(paths), dtype=bool)
    return f


def test_semantic_neighbors_rank_by_cosine(tmp_path):
    sources = synthetic_sources(3, tmp_path / "src")
    build(sources, tmp_path / "out")
    paths = sorted((tmp_path / "out" / "images").rglob("*.*"))
    index = LibraryIndex(_with_embeddings(paths))
    query = paths.index(tmp_path / "out" / "images" / sources[0].stem / "original.jpg")
    hits = index.neighbors(query, method="semantic", k=10, min_cosine=0.5)
    cosines = [s.cosine for _, s in hits]
    assert all(c is not None and c >= 0.5 for c in cosines)
    assert cosines == sorted((c for c in cosines if c is not None), reverse=True)
    # The closest neighbours are variants of the same source photo.
    assert paths[hits[0][0]].parent.name == sources[0].stem


def test_pairs_include_embedding_candidates_beyond_hash_radius(tmp_path):
    sources = synthetic_sources(2, tmp_path / "src")
    build(sources, tmp_path / "out")
    paths = sorted((tmp_path / "out" / "images").rglob("*.*"))
    index = LibraryIndex(_with_embeddings(paths))
    hash_only = {(i, j) for i, j, _ in index.pairs(radius=0, k=1, min_cosine=1.01)}
    with_emb = index.pairs(radius=0, k=10, min_cosine=0.5)
    assert {(i, j) for i, j, _ in with_emb} > hash_only
    assert all(s.cosine is not None for _, _, s in with_emb)


def test_missing_embeddings_give_no_cosine(tmp_path):
    sources = synthetic_sources(1, tmp_path / "src")
    build(sources, tmp_path / "out")
    paths = sorted((tmp_path / "out" / "images").rglob("*.*"))[:3]
    f = _with_embeddings(paths)
    assert f.has_emb is not None
    f.has_emb[1] = False
    index = LibraryIndex(f)
    by_row = dict(index.neighbors(0, radius=64))
    assert by_row[1].cosine is None and by_row[2].cosine is not None
    assert index.neighbors(1, method="semantic") == []
