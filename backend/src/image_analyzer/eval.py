"""Measure the matcher against a labelled fixture set (see devtools/make_fixtures.py).

    uv run python -m image_analyzer.eval ../fixtures

Scores every pair of fixture images and reports:
  1. Per variant: the verdicts it got against its group's original, versus the EXPECTED label.
  2. Unrelated pairs (different groups): how many were wrongly called a match.
  3. A pHash threshold sweep: recall per variant and false matches at each distance, which is
     what to look at when choosing thresholds in search/verdict.py.

Fingerprints are cached in <fixtures>/features.npz, so re-running after changing classify()
takes seconds.

Source photos that genuinely belong together (burst shots, the same scene) can be listed in
<fixtures>/related.json as {"related": [["IMG_0030", "IMG_0031", ...], ...]}. Pairs across those
groups are reported separately as expected "similar" matches, not as false matches.
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from image_analyzer.core.config import settings
from image_analyzer.pipeline.decode import open_for_features
from image_analyzer.pipeline.embeddings import as_batch, get_extractor, prepare
from image_analyzer.pipeline.hashing import as_codes, perceptual_hashes
from image_analyzer.pipeline.process import FEATURES_VERSION, sha256_file
from image_analyzer.search.index import best_orientation
from image_analyzer.search.verdict import LEVEL_RANK, PairScores, classify

SWEEP = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28]


def _fingerprint(path: Path) -> tuple[str, bytes, bytes, bytes]:
    img, _, _ = open_for_features(path)  # the scan's exact decode path
    return (sha256_file(path), *perceptual_hashes(img), prepare(img))


def load_features(fixtures: Path, paths: list[str], workers: int):
    """Returns (sha, phash, dhash, emb, model name); cached in features.npz."""
    cache = fixtures / "features.npz"
    manifest_mtime = (fixtures / "manifest.json").stat().st_mtime_ns
    if cache.exists():
        c = np.load(cache)
        if (int(c["manifest_mtime"]) == manifest_mtime and int(c["version"]) == FEATURES_VERSION
                and str(c["model"]) == settings.embedder):
            return list(c["sha"]), c["phash"], c["dhash"], c["emb"], str(c["model_name"])

    print(f"fingerprinting {len(paths)} images with {workers} workers…")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_fingerprint, [fixtures / p for p in paths], chunksize=8))
    sha = [r[0] for r in results]
    phash, dhash = as_codes([r[1] for r in results]), as_codes([r[2] for r in results])

    extractor = get_extractor(settings.embedder)
    if extractor is None:
        raise SystemExit(f"embedder {settings.embedder!r} unavailable; see /api/health for the error")
    print(f"embedding with {extractor.name} on {extractor.device}…")
    emb = np.concatenate([
        extractor.embed(as_batch([r[3] for r in results[k:k + settings.embed_batch]]))
        for k in range(0, len(results), settings.embed_batch)
    ])
    np.savez(cache, sha=np.array(sha), phash=phash, dhash=dhash, emb=emb, model=settings.embedder,
             model_name=extractor.name, manifest_mtime=manifest_mtime, version=FEATURES_VERSION)
    return sha, phash, dhash, emb, extractor.name


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("fixtures", type=Path, nargs="?", default=Path("../fixtures"))
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = p.parse_args()

    manifest = json.loads((args.fixtures / "manifest.json").read_text())
    entries = manifest["images"]
    expected = manifest["expected"]
    sha, phash, dhash, emb, model_name = load_features(args.fixtures, [e["path"] for e in entries], args.workers)

    n = len(entries)
    i, j = np.triu_indices(n, k=1)
    pd, dd, orient = best_orientation(phash[i], phash[j], dhash[i], dhash[j])
    cos = np.einsum("nd,nd->n", emb[i], emb[j])

    def scores(k: int | np.integer) -> PairScores:
        return PairScores(same_sha=sha[i[k]] == sha[j[k]], phash=int(pd[k]), dhash=int(dd[k]),
                          orientation=int(orient[k]), cosine=float(cos[k]))

    group = np.array([e["group"] for e in entries])
    variant = np.array([e["variant"] for e in entries])
    same_group = group[i] == group[j]

    related_file = args.fixtures / "related.json"
    clusters = json.loads(related_file.read_text())["related"] if related_file.exists() else []
    cluster_of = {g: n for n, members in enumerate(clusters) for g in members}
    cluster = np.array([cluster_of.get(g, -1 - k) for k, g in enumerate(group)])  # -1-k: own cluster
    related = ~same_group & (cluster[i] == cluster[j])

    # (a) each variant against its own group's original
    with_original = same_group & ((variant[i] == "original") | (variant[j] == "original"))
    other = np.where(variant[i] == "original", variant[j], variant[i])
    by_variant: dict[str, list[tuple[int, str]]] = defaultdict(list)
    variant_cos: dict[str, list[float]] = defaultdict(list)
    for k in np.flatnonzero(with_original):
        by_variant[str(other[k])].append((int(pd[k]), classify(scores(k))))
        variant_cos[str(other[k])].append(float(cos[k]))

    print(f"\n{len(set(group))} groups, {n} images, {len(i):,} pairs; embeddings: {model_name}\n")
    print("1. Variant vs its original")
    print(f"   {'variant':<14}{'expected':<16}{'correct':>9}{'pHash median':>14}{'max':>6}   verdicts")
    correct_total = graded_total = 0
    for v in manifest["variants"]:
        if v == "original" or v not in by_variant:
            continue
        rows = by_variant[v]
        verdicts = Counter(level for _, level in rows)
        want = expected.get(v)
        correct = verdicts.get(want, 0) if want else 0
        correct_total += correct
        graded_total += len(rows) if want else 0
        dists = [d for d, _ in rows]
        summary = ", ".join(f"{lvl} {cnt}" for lvl, cnt in verdicts.most_common())
        print(f"   {v:<14}{want or '-':<16}{correct:>4}/{len(rows):<4}{np.median(dists):>14.0f}"
              f"{max(dists):>6}   {summary}")

    # (b) unrelated pairs, and pairs from related source photos
    cross = np.flatnonzero(~same_group & ~related)
    false_matches = Counter()
    for k in cross:
        level = classify(scores(k))
        if LEVEL_RANK[level] > LEVEL_RANK["different"]:
            false_matches[level] += 1
    print(f"\n2. Unrelated pairs: {len(cross):,}; wrongly matched: {sum(false_matches.values())}"
          + (f" ({dict(false_matches)})" if false_matches else ""))
    print(f"   closest unrelated pair: pHash {int(pd[cross].min())}" if len(cross) else "")
    rel = np.flatnonzero(related)
    if len(rel):
        rel_levels = Counter(classify(scores(k)) for k in rel)
        print(f"   Related pairs (related.json, {len(clusters)} cluster(s)): {len(rel):,}; verdicts: "
              + ", ".join(f"{lvl} {cnt}" for lvl, cnt in rel_levels.most_common())
              + f"; pHash median {int(np.median(pd[rel]))}")

    # (c) threshold sweep on pHash alone
    print("\n3. pHash threshold sweep (share of each variant within distance t of its original;")
    print("   last column: unrelated pairs within t, i.e. false matches at that threshold)")
    shown = [v for v in manifest["variants"] if v in by_variant]
    print("   " + f"{'t':>3}" + "".join(f"{v[:9]:>10}" for v in shown) + f"{'unrelated':>11}")
    cross_d = pd[cross]
    for t in SWEEP:
        cells = "".join(f"{np.mean([d <= t for d, _ in by_variant[v]]):>10.0%}" for v in shown)
        print(f"   {t:>3}{cells}{int((cross_d <= t).sum()):>11}")

    # (d) pHash and dHash together: does requiring dHash agreement cut false matches?
    near = [k for k in np.flatnonzero(with_original) if expected.get(str(other[k])) == "near_duplicate"]
    rotated_cross = cross[orient[cross] != 0]
    print("\n4. Rule 'pHash <= t AND dHash <= d': share of expected near-duplicates caught /")
    print("   unrelated pairs matched (of which needed a rotation or mirror)")
    d_limits = [6, 10, 14, 18, 64]
    print("   " + f"{'t':>3}" + "".join(f"{'d<=' + str(d) if d < 64 else 'any d':>19}" for d in d_limits))
    for t in (8, 10, 12, 14, 16, 18):
        cells = ""
        for d in d_limits:
            caught = np.mean([(pd[k] <= t) & (dd[k] <= d) for k in near]) if near else 0.0
            false = int(((pd[cross] <= t) & (dd[cross] <= d)).sum())
            false_rot = int(((pd[rotated_cross] <= t) & (dd[rotated_cross] <= d)).sum())
            cells += f"{caught:.0%} / {false} ({false_rot})".rjust(19)
        print(f"   {t:>3}{cells}")

    # (e) embedding cosine: where should "similar" start?
    print(f"\n5. Embedding cosine ({model_name})")
    print("   Each variant vs its original (min / median):")
    print("   " + "  ".join(f"{v} {min(variant_cos[v]):.2f}/{np.median(variant_cos[v]):.2f}"
                          for v in manifest["variants"] if v in variant_cos))
    pct = lambda a, q: float(np.percentile(a, q)) if len(a) else float("nan")  # noqa: E731
    print(f"   Related pairs (bursts):  min {pct(cos[rel], 0):.2f}  p10 {pct(cos[rel], 10):.2f}  "
          f"median {pct(cos[rel], 50):.2f}" if len(rel) else "   Related pairs: none (add fixtures/related.json)")
    print(f"   Unrelated pairs:         median {pct(cos[cross], 50):.2f}  p99 {pct(cos[cross], 99):.2f}  "
          f"p99.9 {pct(cos[cross], 99.9):.2f}  max {pct(cos[cross], 100):.2f}")
    print("   Threshold sweep: share of related pairs >= c / unrelated pairs >= c")
    for c in (0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95):
        rel_share = f"{np.mean(cos[rel] >= c):.0%}" if len(rel) else "-"
        print(f"   c={c:.2f}  related {rel_share:>5}   unrelated {int((cos[cross] >= c).sum()):>6}")

    if graded_total:
        print(f"\nOverall: {correct_total}/{graded_total} variant pairs match their EXPECTED label "
              f"({correct_total / graded_total:.0%}); {sum(false_matches.values())} false matches.")


if __name__ == "__main__":
    main()
