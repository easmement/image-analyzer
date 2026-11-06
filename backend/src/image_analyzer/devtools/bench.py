"""Scan benchmarks.

    # 1. Build a set: 2,000 images in <out>/a (for tuning) + the rest in <out>/b.
    uv run python -m image_analyzer.devtools.bench make-set --source ~/Pictures/sample \\
        --out ~/.cache/image-analyzer-bench --count 10000
    # 2. One timed first scan of a folder (fresh data dir each time, model preloaded):
    uv run python -m image_analyzer.devtools.bench run ~/.cache/image-analyzer-bench/a
    # 3. A sweep over workers / embed batch / embedder, one subprocess per configuration:
    uv run python -m image_analyzer.devtools.bench sweep ~/.cache/image-analyzer-bench/a

Note: after the first read, files come from the OS page cache, so these are warm-cache numbers.
Dropping caches needs root (echo 3 > /proc/sys/vm/drop_caches).
"""

import argparse
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SOURCE_EXTS = {".jpg", ".jpeg", ".png"}


def _variant(job: tuple[Path, Path, int]) -> None:
    from PIL import Image, ImageEnhance, ImageOps

    src, dest, seed = job
    rng = random.Random(seed)
    with Image.open(src) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    w, h = img.size
    keep = rng.uniform(0.7, 1.0)  # crop to 70-100% per side, then rescale: a distinct-looking photo
    cw, ch = int(w * keep), int(h * keep)
    x, y = rng.randint(0, w - cw), rng.randint(0, h - ch)
    img = img.crop((x, y, x + cw, y + ch)).resize((w, h), Image.Resampling.BILINEAR)
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.85, 1.15))
    img.save(dest, "JPEG", quality=rng.randint(80, 95))


def make_set(source: Path, out: Path, count: int, tuning: int) -> None:
    sources = sorted(f for f in source.expanduser().iterdir() if f.suffix.lower() in SOURCE_EXTS)
    out = out.expanduser()
    jobs = []
    for n, src in zip(range(count), itertools.cycle(sources)):
        folder = out / ("a" if n < tuning else "b") / f"{n // 500:03d}"
        folder.mkdir(parents=True, exist_ok=True)
        jobs.append((src, folder / f"bench_{n:05d}.jpg", n))
    t = time.time()
    with ProcessPoolExecutor() as pool:
        list(pool.map(_variant, jobs, chunksize=16))
    size = sum(f.stat().st_size for f in out.rglob("*.jpg"))
    print(f"wrote {count} images ({size / 2**30:.1f} GB) to {out} in {time.time() - t:.0f}s "
          f"({tuning} in a/ for tuning)")


def run(root: Path) -> dict:
    """One first scan, in this process. IMAGE_ANALYZER_* must be set before this is called."""
    from image_analyzer.core.config import settings
    from image_analyzer.core.db import init_db, transaction
    from image_analyzer.jobs.runner import jobs
    from image_analyzer.pipeline.embeddings import get_extractor

    init_db()
    t = time.perf_counter()
    get_extractor(settings.embedder)  # load the model up front so it isn't in the scan time
    model_load = time.perf_counter() - t
    with transaction() as conn:
        lib = conn.execute("INSERT INTO libraries (root_path, name) VALUES (?, 'bench')",
                           (str(root.resolve()),)).lastrowid
    job = jobs.start_scan(lib, root.resolve())  # type: ignore[arg-type]
    while job.status == "running":
        time.sleep(0.2)
    snap = job.snapshot()
    return {
        "status": snap.status, "images": snap.done, "failed": snap.failed,
        "elapsed_s": snap.elapsed_s, "images_per_s": round(snap.done / (snap.elapsed_s or 1), 1),
        "timings": snap.timings, "model_load_s": round(model_load, 1),
        "config": {"workers": settings.workers, "embed_batch": settings.embed_batch,
                   "write_batch": settings.write_batch, "embedder": settings.embedder},
    }


def _run_subprocess(root: Path, env_overrides: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="ia-bench-", dir=Path.home() / ".cache") as data_dir:
        env = {**os.environ, **env_overrides, "IMAGE_ANALYZER_DATA_DIR": data_dir}
        out = subprocess.run([sys.executable, "-m", "image_analyzer.devtools.bench", "run", str(root), "--json"],
                             env=env, capture_output=True, text=True, check=True)
        return json.loads(out.stdout.strip().splitlines()[-1])


def sweep(root: Path, workers: list[int], batches: list[int], embedders: list[str]) -> None:
    print(f"{'embedder':<8}{'workers':>8}{'batch':>7}{'img/s':>8}{'total s':>9}   stage seconds")
    for embedder, w, b in itertools.product(embedders, workers, batches):
        if embedder == "none" and b != batches[0]:
            continue  # batch size only matters when embedding
        r = _run_subprocess(root, {"IMAGE_ANALYZER_EMBEDDER": embedder, "IMAGE_ANALYZER_WORKERS": str(w),
                                   "IMAGE_ANALYZER_EMBED_BATCH": str(b)})
        stages = "  ".join(f"{k} {v:.1f}" for k, v in r["timings"].items() if k != "model_load")
        print(f"{embedder:<8}{w:>8}{b:>7}{r['images_per_s']:>8.1f}{r['elapsed_s']:>9.1f}   {stages}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-set")
    m.add_argument("--source", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--count", type=int, default=10_000)
    m.add_argument("--tuning", type=int, default=2_000)
    r = sub.add_parser("run")
    r.add_argument("root", type=Path)
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("sweep")
    s.add_argument("root", type=Path)
    s.add_argument("--workers", type=lambda v: [int(x) for x in v.split(",")], default=[4, 8, 10, 12])
    s.add_argument("--batches", type=lambda v: [int(x) for x in v.split(",")], default=[32])
    s.add_argument("--embedders", type=lambda v: v.split(","), default=["none", "dinov2"])
    args = p.parse_args()

    if args.cmd == "make-set":
        make_set(args.source, args.out, args.count, args.tuning)
    elif args.cmd == "run":
        result = run(args.root.expanduser())
        print(json.dumps(result) if args.json else json.dumps(result, indent=2))
    else:
        sweep(args.root.expanduser(), args.workers, args.batches, args.embedders)


if __name__ == "__main__":
    main()
