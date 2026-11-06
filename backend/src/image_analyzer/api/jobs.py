from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from image_analyzer.core.models import Job
from image_analyzer.jobs.runner import TERMINAL, jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str) -> Job:
    if (job := jobs.get(job_id)) is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.delete("/{job_id}", status_code=202)
def cancel_job(job_id: str) -> Job:
    job = jobs.jobs.get(job_id)
    if job is None or job.status != "running":
        raise HTTPException(409, "Job is not running")
    job.cancel.set()
    return job.snapshot()


@router.get("/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Server-Sent Events: one `data:` line per progress update; the stream ends when the job does."""
    job = jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} not running in this server")

    async def stream() -> AsyncIterator[str]:
        q = jobs.subscribe(job)
        try:
            while True:
                snapshot = await q.get()
                yield f"data: {snapshot.model_dump_json()}\n\n"
                if snapshot.status in TERMINAL:
                    return
        finally:
            jobs.unsubscribe(job, q)

    # no-transform/X-Accel-Buffering stop proxies (including Next's dev rewrite) from buffering.
    headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)
