"""Background scan jobs.

A scan runs in its own thread, which fans the per-file work out to a process pool (decode, hash,
thumbnail). Finished rows go in batches to a second thread that embeds them on the GPU and writes
them to the database, so the CPU workers and the GPU run at the same time instead of taking turns.
Progress is pushed to the event loop with call_soon_threadsafe, where each SSE client has an
asyncio.Queue.
"""

import asyncio
import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from image_analyzer.core.config import settings
from image_analyzer.core.db import connect, transaction
from image_analyzer.core.models import Job as JobModel
from image_analyzer.pipeline.embeddings import Extractor, as_batch, get_extractor
from image_analyzer.pipeline.process import FEATURES_VERSION, HASHES_VERSION, process_file
from image_analyzer.pipeline.scanner import FileStat, diff, walk

TERMINAL = {"completed", "cancelled", "failed"}
PUBLISH_INTERVAL = 0.1  # seconds; caps progress events at ~10/s

UPSERT = """
INSERT INTO images (library_id, rel_path, size_bytes, mtime_ns, sha256, width, height, format,
                    status, error, phash8, dhash8, features_version, embedding, embedding_model)
VALUES (:library_id, :rel_path, :size_bytes, :mtime_ns, :sha256, :width, :height, :format,
        :status, :error, :phash8, :dhash8, :features_version, :embedding, :embedding_model)
ON CONFLICT (library_id, rel_path) DO UPDATE SET
    size_bytes = excluded.size_bytes, mtime_ns = excluded.mtime_ns, sha256 = excluded.sha256,
    width = excluded.width, height = excluded.height, format = excluded.format,
    status = excluded.status, error = excluded.error, phash8 = excluded.phash8,
    dhash8 = excluded.dhash8, features_version = excluded.features_version,
    embedding = excluded.embedding, embedding_model = excluded.embedding_model,
    indexed_at = datetime('now')
"""


class JobConflict(Exception):
    pass


@dataclass
class Job:
    id: str
    kind: str
    library_id: int
    status: str = "running"
    total: int = 0
    done: int = 0
    failed: int = 0
    message: str | None = None
    current: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    subscribers: set[asyncio.Queue] = field(default_factory=set, repr=False)
    last_publish: float = field(default=0.0, repr=False)
    started: float = field(default_factory=time.monotonic, repr=False)
    finished: float | None = field(default=None, repr=False)
    timings: dict[str, float] = field(default_factory=dict, repr=False)

    @contextmanager
    def timed(self, stage: str) -> Iterator[None]:
        t = time.perf_counter()
        try:
            yield
        finally:
            self.timings[stage] = self.timings.get(stage, 0.0) + time.perf_counter() - t

    def snapshot(self) -> JobModel:
        elapsed = (self.finished or time.monotonic()) - self.started
        return JobModel(
            id=self.id, kind=self.kind, library_id=self.library_id, status=self.status,  # type: ignore[arg-type]
            total=self.total, done=self.done, failed=self.failed,
            message=self.message, current=self.current, elapsed_s=round(elapsed, 2),
            timings={k: round(v, 2) for k, v in self.timings.items()},
        )


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called at startup. Jobs still 'running' in the DB died with a previous server."""
        self.loop = loop
        with transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'failed', message = 'server restarted', "
                "finished_at = datetime('now') WHERE status = 'running'"
            )

    def running_for(self, library_id: int) -> Job | None:
        return next(
            (j for j in self.jobs.values() if j.library_id == library_id and j.status == "running"),
            None,
        )

    def get(self, job_id: str) -> JobModel | None:
        if job := self.jobs.get(job_id):
            return job.snapshot()
        with transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return JobModel(**dict(row)) if row else None

    def start_scan(self, library_id: int, root: Path, full: bool = False, retry_errors: bool = False) -> Job:
        with self._lock:
            if running := self.running_for(library_id):
                raise JobConflict(running.id)
            job = Job(id=uuid.uuid4().hex, kind="scan", library_id=library_id)
            self.jobs[job.id] = job
        with transaction() as conn:
            conn.execute(
                "INSERT INTO jobs (id, kind, library_id, status) VALUES (?, ?, ?, 'running')",
                (job.id, job.kind, library_id),
            )
        threading.Thread(target=self._run_scan, args=(job, root, full, retry_errors), daemon=True).start()
        return job

    # --- event fan-out -------------------------------------------------------------------

    def subscribe(self, job: Job) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        job.subscribers.add(q)
        q.put_nowait(job.snapshot())
        return q

    def unsubscribe(self, job: Job, q: asyncio.Queue) -> None:
        job.subscribers.discard(q)

    def _publish(self, job: Job, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - job.last_publish < PUBLISH_INTERVAL:
            return
        job.last_publish = now
        if self.loop is None:
            return
        snapshot = job.snapshot()
        for q in list(job.subscribers):
            self.loop.call_soon_threadsafe(q.put_nowait, snapshot)

    # --- the scan itself (runs in a worker thread) ---------------------------------------

    @staticmethod
    def _flush(job: Job, conn, batch: list[dict], extractor: Extractor | None, target_version: int) -> None:
        """Embed the batch on the GPU (in model-sized chunks), then write it in one transaction."""
        to_embed = [row for row in batch if row.get("embed_input")]
        with job.timed("embed"):
            for start in range(0, len(to_embed), settings.embed_batch):
                chunk = to_embed[start:start + settings.embed_batch]
                assert extractor is not None
                vectors = extractor.embed(as_batch([row["embed_input"] for row in chunk]))
                for row, vec in zip(chunk, vectors):
                    row["embedding"] = vec.astype(np.float16).tobytes()
                    row["embedding_model"] = extractor.name
        for row in batch:
            row.pop("embed_input", None)
            row.setdefault("embedding", None)
            row.setdefault("embedding_model", None)
            # Rows that should have an embedding but don't stay at the hashes version, so a
            # later scan retries them.
            row["features_version"] = (
                HASHES_VERSION if row["status"] == "ok" and target_version == FEATURES_VERSION
                and row["embedding"] is None else target_version
            )
        with job.timed("write"):
            conn.executemany(UPSERT, batch)
            conn.commit()
        batch.clear()

    def _run_scan(self, job: Job, root: Path, full: bool, retry_errors: bool = False) -> None:
        conn = connect()
        try:
            with job.timed("walk"):
                files = list(walk(root))
            existing = {
                # retry_errors: version 0 makes unreadable rows look stale, so they're retried.
                r["rel_path"]: (r["id"], r["size_bytes"], r["mtime_ns"],
                                0 if retry_errors and r["status"] == "error" else r["features_version"])
                for r in conn.execute(
                    "SELECT id, rel_path, size_bytes, mtime_ns, features_version, status FROM images "
                    "WHERE library_id = ?",
                    (job.library_id,),
                )
            }
            # Load the model before deciding what's stale: if it can't load, aim for hashes only.
            with job.timed("model_load"):
                extractor = get_extractor(settings.embedder)
            target_version = FEATURES_VERSION if extractor else HASHES_VERSION
            changes = diff(files, existing, target_version, full)
            if changes.removed_ids:
                conn.executemany("DELETE FROM images WHERE id = ?", [(i,) for i in changes.removed_ids])
                conn.commit()
            job.total = len(changes.to_process)
            self._publish(job, force=True)

            # Embed + write thread. The queue holds at most 2 batches: if the GPU falls behind,
            # put() blocks and the workers pause, which bounds memory.
            batches: queue.Queue[list[dict] | None] = queue.Queue(maxsize=2)
            writer_error: list[BaseException] = []

            def embed_and_write() -> None:
                while (pending := batches.get()) is not None:
                    try:
                        if not writer_error:
                            self._flush(job, conn, pending, extractor, target_version)
                    except BaseException as e:  # noqa: BLE001 - re-raised in the scan thread
                        writer_error.append(e)

            writer = threading.Thread(target=embed_and_write, name=f"scan-{job.id[:8]}-writer", daemon=True)
            writer.start()

            def hand_off(rows: list[dict]) -> None:
                with job.timed("handoff"):  # time blocked because the writer is behind
                    batches.put(rows)

            batch: list[dict] = []
            todo = iter(changes.to_process)
            in_flight: dict[Future, FileStat] = {}
            # Bounded window: the GPU is slower than the decoders, so submitting everything up
            # front would pile finished results (each with a 150 KB model input) up in memory.
            max_in_flight = settings.workers * 4
            with ProcessPoolExecutor(max_workers=settings.workers) as pool:

                def top_up() -> None:
                    while len(in_flight) < max_in_flight and (f := next(todo, None)):
                        fut = pool.submit(process_file, root / f.rel_path, settings.thumbs_dir,
                                          settings.thumbnail_size, extractor is not None)
                        in_flight[fut] = f

                top_up()
                while in_flight and not job.cancel.is_set():
                    with job.timed("wait"):
                        finished, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                    for fut in finished:
                        f = in_flight.pop(fut)
                        result = {"sha256": None, "width": None, "height": None, "format": None,
                                  "error": None, "phash8": None, "dhash8": None, **fut.result()}
                        batch.append({"library_id": job.library_id, "rel_path": f.rel_path,
                                      "size_bytes": f.size_bytes, "mtime_ns": f.mtime_ns, **result})
                        job.done += 1
                        job.failed += result["status"] == "error"
                        job.current = f.rel_path
                    if len(batch) >= settings.write_batch:
                        hand_off(batch)
                        batch = []
                    if writer_error:
                        raise writer_error[0]
                    self._publish(job)
                    top_up()
                if job.cancel.is_set():
                    pool.shutdown(cancel_futures=True)
            if batch:
                hand_off(batch)
            batches.put(None)  # tell the writer we're done, then wait for it to drain
            with job.timed("drain"):
                writer.join()
            if writer_error:
                raise writer_error[0]

            job.current = None
            job.message = f"{changes.unchanged} unchanged, {len(changes.removed_ids)} removed"
            if job.cancel.is_set():
                job.status = "cancelled"
            else:
                conn.execute("UPDATE libraries SET last_scan_at = datetime('now') WHERE id = ?",
                             (job.library_id,))
                job.status = "completed"
        except Exception as e:  # report any failure on the job instead of losing it in a thread
            job.status = "failed"
            job.message = f"{type(e).__name__}: {e}"
        finally:
            job.finished = time.monotonic()
            conn.execute(
                "UPDATE jobs SET status = ?, total = ?, done = ?, failed = ?, message = ?, "
                "finished_at = datetime('now') WHERE id = ?",
                (job.status, job.total, job.done, job.failed, job.message, job.id),
            )
            conn.commit()
            conn.close()
            self._publish(job, force=True)


jobs = JobManager()
