# Image Analyzer

Find exact duplicates, near-duplicates and visually similar images in local folders.
Python (FastAPI) backend, Next.js + MUI frontend. See [DESIGN.md](DESIGN.md) and [PLAN.md](PLAN.md).

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.14 is fetched automatically)
- Node.js 20+ and npm
- Optional: an NVIDIA GPU with the Windows driver (WSL) or Linux driver. CPU works, just slower.

## Quick start

```bash
make install   # uv sync + npm install (first run downloads ~3 GB of PyTorch/CUDA)
make dev       # backend on http://127.0.0.1:8001, UI on http://localhost:3000
```

The UI calls the backend through a Next.js rewrite (`/api/*` → `:8001`), so the backend only
listens on localhost. Set `IMAGE_ANALYZER_API` to point the frontend at a different backend.

## Common tasks

| Command | What it does |
|---|---|
| `make test` | Backend pytest, frontend typecheck and lint |
| `make gen` | Regenerate frontend API types from the running backend's OpenAPI schema |
| `make fixtures` | Generate a synthetic labelled test set in `fixtures/` |
| `make fixtures SOURCE=~/Pictures/sample` | Build the test set from your own photos (~30 recommended) |
| `make eval` | Score the matcher against the fixture labels (uses the saved thresholds) |
| `make bench-set` / `make bench` / `make bench-clean` | Build a 10k-image benchmark set (~4 GB), time scans, delete the set |

## Configuration

| Variable | Default |
|---|---|
| `IMAGE_ANALYZER_DATA_DIR` | `~/.cache/image-analyzer` (database, thumbnails, indexes) |
| `IMAGE_ANALYZER_HOST` / `IMAGE_ANALYZER_PORT` | `127.0.0.1` / `8001` |
| `IMAGE_ANALYZER_EMBEDDER` | `dinov2` (`fake` for tests, `none` to skip embeddings) |
| `IMAGE_ANALYZER_WORKERS` | CPU cores − 4 (fastest with embeddings on 12 threads; see DESIGN.md §6) |
| `IMAGE_ANALYZER_EMBED_BATCH` / `IMAGE_ANALYZER_WRITE_BATCH` | `32` / `200` |
| `IMAGE_ANALYZER_API` (frontend) | `http://127.0.0.1:8001` |

Match thresholds are edited on the **Settings** page and saved to `<data dir>/thresholds.json`.
