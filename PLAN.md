# Image Analyzer: Implementation Plan

This is the build order for [DESIGN.md](DESIGN.md). Each phase ends with something that runs end to
end, so you can stop after any phase and have a usable tool.

## Phase 0: Project setup

- [x] `backend/`: `uv init --package image-analyzer`. Add FastAPI, Pillow, imagehash, NumPy and
      pytest. Add a `/api/health` endpoint that reports the Python version, data dir, and
      `torch.cuda.is_available()`.
- [x] **Check wheels:** `uv add torch faiss-cpu` on Python 3.14. *Result: torch 2.15.0+cu132 and
      faiss-cpu 1.15.1 install on 3.14, and CUDA works on the GTX 1650 (`sm_75`), so no pin is
      needed.*
- [x] `frontend/`: `npx create-next-app@latest` (TypeScript, App Router, ESLint). Add MUI and
      TanStack Query, and configure `rewrites` to `:8001`. *Got Next.js 16.4.5 and MUI 9.5.*
- [x] Add an `openapi-typescript` script (`npm run gen:api`) that writes `src/lib/types.gen.ts`.
- [x] Add a root `README.md` with a dev command for each side, and a `Makefile` with `dev`,
      `test`, `gen` and `fixtures`.
- [x] **Build a test fixture set:** `image_analyzer.devtools.make_fixtures` takes source photos
      (or `--synthetic N`) and generates 11 known variants each, including an EXIF-rotated copy. The
      other groups serve as the unrelated images.
- [x] **Fill in the ground-truth labels** (`EXPECTED` in `make_fixtures.py`). `copy` is `exact`,
      and all other variants, including `rot90` and `mirror`, are `near_duplicate`. The evaluation
      compares levels strictly (an `exact` result doesn't satisfy a `near_duplicate` label).
- [x] **Gap:** there were no `similar` fixtures. Partly filled: `fixtures/related.json` marks the
      `IMG_0030`–`IMG_0036` burst from `~/Pictures/sample`. More related sets would help Phase 3.

**Exit:** the frontend at `:3000` shows `/api/health` from the backend through the proxy.

## Phase 1: Scan, exact duplicates, gallery

- [x] SQLite schema and migrations (`core/db.py`, versioned with `PRAGMA user_version`).
- [x] `pipeline/decode.py`: safe open, EXIF transpose, RGB conversion, pixel limit.
- [x] `pipeline/scanner.py`: recursive walk, extension filter, new/changed/removed diff on
      `(size, mtime_ns)`. Symlinks and hidden files are skipped. Removed files are deleted from
      the index rather than marked.
- [x] SHA-256, dimensions and thumbnails in a `ProcessPoolExecutor`, from one decode per file.
      Thumbnails are named by SHA-256, so duplicates and moved files share them.
- [x] Job runner with SSE progress and cancellation. Checked streaming through the Next.js proxy:
      ~10 events/s, not buffered.
- [x] Endpoints: libraries (with `active_job_id`), scan, jobs, the image list (keyset cursor),
      thumbnail, file.
- [x] UI: dashboard (add a library, scan, progress bar, remove) and a virtualized gallery with an
      unreadable-files filter.
- [x] `/api/groups?level=exact`, the duplicates page, and CSV export (moved up from Phase 4).
- [x] Tests: the scanner diff, symlink skipping, a corrupt file doesn't fail the job, incremental
      rescans, pagination, SSE (16 tests).
- [x] **`pick_best()` in `search/grouping.py`**: keep the copy with the most pixels, then the
      largest file, then a camera name (`IMG_nnnn.jpg`), then the shallowest folder, then the oldest
      file, with the path as the final tie-break. Covered by `tests/test_grouping.py`.
- [ ] Check the UI in a browser. No headless browser is installed, so this hasn't been done.

Measured: a full rescan of 1,100 small synthetic images took 0.85 s with thumbnails cached.

**Exit:** scan a real folder, watch progress live, browse thumbnails, and see the exact-duplicate
groups.

## Phase 2: Near-duplicates (perceptual hashing)

- [x] pHash and dHash computed in the same pass as Phase 1. Instead of needing `?full=true`, a
      `features_version` column makes any scan reprocess rows from an older pipeline.
- [x] FAISS `IndexBinaryFlat` over the pHashes, cached per library and rebuilt when its rows
      change. `/api/images/{id}/similar`.
- [x] **Orientation-invariant matching:** all 8 orientation hashes are computed **at scan time**
      (rotating a 32×32 thumbnail makes this nearly free) and stored as 64-byte blobs, so grouping
      never re-decodes images. Pair distance is the minimum over orientations, in both directions.
- [ ] `search/verdict.py` `classify()` (TODO(human)): the scores → verdict rule. A placeholder
      (`pHash ≤ 10`) is in place.
- [x] `search/grouping.py`: candidate pairs → union-find clusters, `level=near_duplicate`.
- [x] UI: image detail page with matches (verdict, distances, rotation), gallery tiles link to it,
      and the duplicates page has an Exact / Near-duplicate selector.
- [x] **Evaluation harness:** `make eval`. Per-variant verdicts, unrelated-pair false matches, a
      pHash sweep and a pHash × dHash table. `fixtures/related.json` marks related source photos
      (the `IMG_0030`–`IMG_0036` burst) so they aren't counted as false matches.

Findings on `~/Pictures/sample` (47 photos, 517 fixtures):
- Every variant except `crop10` sits at pHash ≤ 6. `crop10` has a median of 10 and a maximum of 16.
- `IMG_0030`–`IMG_0036` is a burst of one scene (pHash 2–8 apart). These are real `similar` cases
  for Phase 3, and union-find chains them into one 77-image near-duplicate group under the
  placeholder rule.
- With the placeholder rule, 75 of 128,260 unrelated pairs match; 42 of them needed a rotation or
  mirror. Coincidental rotated matches have high dHash (23–31), while real variants have low dHash.

**Exit:** resized and recompressed copies are grouped together and unrelated images aren't, with the
precision and recall numbers recorded in the README.

## Phase 3: Semantic similarity (embeddings)

- [x] `pipeline/embeddings.py`: an `Extractor` protocol, a DINOv2-S implementation (CUDA if
      available) and a `FakeExtractor` for tests (`IMAGE_ANALYZER_EMBEDDER=dinov2|fake|none`).
      **fp32, not fp16:** on the GTX 1650 (no tensor cores) fp16 ran at 22 images/s against 100.
- [x] A batched GPU stage: the CPU workers prepare the 224×224 input from their single decode, and
      the scan thread embeds batches of 32 before each database write. The work queue is now a
      bounded window (4 × workers), because the GPU is slower than the decoders and results would
      otherwise pile up in memory. Rows that couldn't be embedded keep `features_version = 2` and
      are retried on the next scan.
- [x] `search/index.py` (replaces `perceptual.py`): the pHash index plus a FAISS `IndexFlatIP` over
      embeddings (stored float16 in `images.embedding`). Built in memory, cached per library and
      rebuilt when rows change. It isn't saved to disk, since rebuilding from the database is fast.
- [x] `method=semantic` (with `min_cosine`) on `/similar`, `level=similar` in grouping, and
      `PairScores.cosine`. The `similar` rule in `classify()` is a placeholder (TODO(human)).
- [x] UI: a Near-duplicates / Similar toggle with a min-similarity slider on the detail page, a
      Similar level on the duplicates page, and the embedder status on the health card.
- [x] Evaluation section 5: cosine per variant, for related pairs and unrelated pairs, plus a
      threshold sweep. `related.json` now holds 6 visually verified same-scene clusters.
- [ ] **`classify()` similar rule** (TODO(human)), chosen from the evaluation's section 5.

Findings on `~/Pictures/sample` with DINOv2-small:
- Embeddings ignore edits but not rotation: `rot90` scores cosine 0.35–0.53, so the pHash
  orientation trick stays essential. `crop10` scores 0.84–0.93, which can rescue crops that pHash misses.
- Same-scene shots score 0.91–0.96. Unrelated pairs: median 0.27, p99.9 0.84, max 0.90.
  At cosine ≥ 0.85: 80% of related pairs (about 96% excluding rotated copies) and 49 of 127k unrelated.
- The top "unrelated" pairs before relabelling were all real same-scene shots, so the embeddings
  found exactly what `similar` is for.
- A full scan of 517 images with embeddings takes ~15 s, including ~10 s of model loading.

**Exit:** opening an image shows visually similar photos that perceptual hashing misses, such as
burst shots and crops.

## Phase 4: Compare and search

- [x] `search/compare.py`: B is aligned to A (orientation picked on 64×64 thumbnails, tried only
      when the hashes matched the pair rotated), both resized to A's frame (max side 1024), then
      Gaussian SSIM (scikit-image) with a per-pixel map drawn as a red PNG overlay. Cached per
      (path, sha) pair, since the page makes four requests for one pair.
- [x] `/api/compare` (all scores plus SSIM and changed area) and `/api/compare/image` (aligned A, B
      and the heatmap). Compare page: Side by side / Swipe (drag or arrow keys) / Differences
      views and a score table. Entry points: **Compare** on match cards and **Compare with keeper**
      in duplicate groups.
- [x] `/api/search/image`: multipart upload, decoded and hashed in memory, embedded if the model
      is available, and scored against every row of the chosen libraries. Never stored. Search
      page with drag-and-drop or a file picker. Works through the Next.js proxy (~200 ms per search).
- [ ] Optional: a CLIP extractor and `/api/search/text`. Deferred: needs a second ~600 MB model
      and a second embedding column.
- [x] Group export as CSV (done in Phase 1; `level` option added in Phase 2).

Known limit: compare explains **edits**, not **crops**. A cropped copy is stretched to the
original's frame, so SSIM sees misalignment (`crop10`: SSIM 0.67, "41% changed") rather than
the crop. Lining crops up properly would need feature-based image registration.

**Exit:** pick any two images and see exactly how and where they differ, or drop in an outside image
and find its matches.

## Phase 5: Hardening and performance

- [x] Benchmark the scan on 10k images (Linux filesystem and `/mnt/c`): `devtools/bench.py`
      (`make bench-set`, `make bench`) and per-stage timings on every job. Numbers in DESIGN.md §6.
- [x] Tune. Measured first, then fixed what the timings showed:
      - **CPU and GPU took turns** (total time = CPU time + GPU time): a separate embed-and-write
        thread with a 2-batch queue. 51 → 77 images/s on the 2k set.
      - **Full-resolution decodes for 256-px features:** JPEG `draft()` decodes at ½–⅛ scale
        (`open_for_features`, used by scans, upload search and eval alike). Hashes-only 84 → 199
        images/s; with DINOv2 68 → 90 (now GPU-bound). Evaluation unchanged (456/470); 15 more
        unrelated near-duplicate matches out of 127k. `FEATURES_VERSION` → 6, so every row is redone.
      - **Normalising on the GPU:** +7%. fp16 and batch 64: no gain. `torch.compile`: fails on 3.14.
      - **Workers default cores − 4** (8 here): more workers starve the GPU-feeding thread.
      - **`/mnt/c` listing: threaded `stat()`**, 13.5 s → 0.5 s per 2,000 files.
- [x] Watch mode (`watchdog`, inotify): a per-library toggle and a 5 s debounce, retried if a scan
      is running. Not available for `/mnt/<drive>` (inotify doesn't cross WSL's 9P bridge); the
      UI explains why.
- [x] Error report page (`/libraries/[id]/errors`): grouped by error kind, with a "Retry
      unreadable files" button (`scan?retry_errors=true`).
- [x] Settings page: editable thresholds (saved to `thresholds.json`, applied immediately, read by
      `make eval` too) and the read-only environment configuration. `classify()` keeps its rules;
      only its three numbers moved into `core/thresholds.py`.
- [x] HNSW: the embedding index switches to `IndexHNSWFlat` above 500k embeddings (tested with a
      lowered threshold: 8+ of the top-10 neighbours match exact search). The pHash binary index
      stays exact. Grouping at that scale would need multi-index hashing; not attempted.

## Testing strategy

| Level | What | Tool |
|---|---|---|
| Unit | Hashing, the verdict function, union-find, path safety, scanner diff | pytest |
| Quality | Precision and recall on the generated fixture set; fail if they regress | pytest + eval harness |
| API | Endpoints against a temporary data dir and a fixture library | pytest + FastAPI `TestClient` |
| UI | Gallery, detail and compare flows on the fixture library | Playwright (`webapp-testing` skill) |

## Open decisions

| Decision | Recommendation | Alternative |
|---|---|---|
| Storage | **SQLite** (one file, zero setup) | Postgres + pgvector, since you already run Postgres 18 locally. Worth it if other services need to query the results. |
| Default embedding model | **DINOv2-S** (best for image-to-image matching) | CLIP ViT-B/32, which adds text search |
| File actions | **Read-only + CSV export** in v1 | Move duplicates to a quarantine folder (needs undo and confirmation UX) |
| Repository layout | **One repo** with `backend/` and `frontend/` | Two separate repos |
| Ports | Backend `8001`, frontend `3000` | `fastapidev` already uses `8000`, so this avoids a clash |
