"use client";
import { useEffect, useState } from "react";
import { api, type Job, TERMINAL_STATUSES, urls } from "@/lib/api";

/**
 * Live job progress. Uses Server-Sent Events, and falls back to polling once a second if the
 * stream errors (for example, a proxy that buffers it). Calls onDone once when the job ends.
 */
export function useJobEvents(jobId: string | null | undefined, onDone?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let finished = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    const update = (next: Job) => {
      if (finished) return;
      setJob(next);
      if (TERMINAL_STATUSES.includes(next.status)) {
        finished = true;
        source.close();
        onDone?.(next);
      }
    };

    const poll = async () => {
      try {
        update(await api.job(jobId));
      } catch {}
      if (!finished) pollTimer = setTimeout(poll, 1000);
    };

    const source = new EventSource(urls.jobEvents(jobId));
    source.onmessage = (e) => update(JSON.parse(e.data) as Job);
    source.onerror = () => {
      // EventSource would reconnect forever; switch to polling instead.
      source.close();
      if (!finished) poll();
    };

    return () => {
      finished = true;
      source.close();
      clearTimeout(pollTimer);
    };
    // onDone is intentionally excluded: callers pass inline callbacks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return job;
}
