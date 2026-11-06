import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from image_analyzer import __version__
from image_analyzer.api import compare, groups, health, images, jobs, libraries, search, settings
from image_analyzer.core.db import init_db, transaction
from image_analyzer.core.localhost_only import LocalhostOnlyMiddleware
from image_analyzer.jobs.runner import jobs as job_manager
from image_analyzer.jobs.watcher import can_watch, watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    job_manager.attach(asyncio.get_running_loop())
    with transaction() as conn:
        for row in conn.execute("SELECT id, root_path FROM libraries WHERE watch = 1"):
            root = Path(row["root_path"])
            if root.is_dir() and can_watch(root) is None:
                watcher.watch(row["id"], root)
    yield
    watcher.stop()


app = FastAPI(title="image-analyzer", version=__version__, lifespan=lifespan)
app.add_middleware(LocalhostOnlyMiddleware)  # DNS-rebinding defence; see core/localhost_only.py
for module in (health, libraries, jobs, images, groups, compare, search, settings):
    app.include_router(module.router)
