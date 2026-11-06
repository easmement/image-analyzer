.PHONY: dev backend frontend test gen fixtures install eval bench-set bench bench-clean

install:
	cd backend && uv sync
	cd frontend && npm install

# Run backend (:8001) and frontend (:3000) together; Ctrl-C stops both.
dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run image-analyzer

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest
	cd frontend && npm run typecheck && npm run lint

# Regenerate frontend/src/lib/types.gen.ts (backend must be running).
gen:
	cd frontend && npm run gen:api

# Fixture set for tests and threshold tuning. Real photos: make fixtures SOURCE=~/Pictures/sample
SOURCE ?=
fixtures:
ifeq ($(SOURCE),)
	cd backend && uv run python -m image_analyzer.devtools.make_fixtures --synthetic 12 --out ../fixtures
else
	cd backend && uv run python -m image_analyzer.devtools.make_fixtures --source $(SOURCE) --out ../fixtures
endif

# Score the matcher against the fixture labels (fixtures/ must exist: make fixtures).
eval:
	cd backend && uv run python -m image_analyzer.eval ../fixtures

# Scan benchmarks (see backend/src/image_analyzer/devtools/bench.py). The set is ~4 GB on disk.
BENCH_DIR ?= $(HOME)/.cache/image-analyzer-bench
bench-set:
	cd backend && uv run python -m image_analyzer.devtools.bench make-set --source $(or $(SOURCE),$(HOME)/Pictures/sample) --out $(BENCH_DIR) --count 10000
bench:
	cd backend && uv run python -m image_analyzer.devtools.bench sweep $(BENCH_DIR) --workers 8 --embedders none,dinov2
bench-clean:
	rm -rf $(BENCH_DIR)
