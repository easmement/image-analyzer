"use client";
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "@/components/Link";
import { useJobEvents } from "@/hooks/useJobEvents";
import { api, type Job, type Library, TERMINAL_STATUSES } from "@/lib/api";
import { formatBytes, formatCount, formatTimestamp } from "@/lib/format";

function ScanProgress({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const pct = job.total ? (job.done / job.total) * 100 : 0;
  return (
    <Box sx={{ mt: 2 }}>
      <LinearProgress variant={job.total ? "determinate" : "indeterminate"} value={pct} />
      <Stack direction="row" sx={{ mt: 1, alignItems: "center", gap: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1, minWidth: 0 }} noWrap>
          {job.total
            ? `${formatCount(job.done)} / ${formatCount(job.total)}${job.failed ? ` · ${job.failed} failed` : ""}`
            : "Looking for files…"}
          {job.current && ` · ${job.current}`}
        </Typography>
        <Button size="small" onClick={onCancel}>
          Cancel
        </Button>
      </Stack>
    </Box>
  );
}

export default function LibraryCard({ library }: { library: Library }) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastJob, setLastJob] = useState<Job | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["libraries"] });

  // Either a scan started from this card, or one already running when the page loaded.
  const activeJobId = jobId ?? library.active_job_id;
  const job = useJobEvents(activeJobId, (done) => {
    setJobId(null);
    setLastJob(done);
    refresh();
  });
  // `job` can briefly be the previous, finished job after a new scan starts, so compare ids.
  const current = job?.id === activeJobId ? job : null;
  const running = !!activeJobId && (!current || !TERMINAL_STATUSES.includes(current.status));

  const scan = useMutation({
    mutationFn: (full: boolean) => api.startScan(library.id, { full }),
    onSuccess: (started) => {
      setLastJob(null);
      setJobId(started.id);
    },
  });
  const remove = useMutation({ mutationFn: () => api.deleteLibrary(library.id), onSuccess: refresh });
  const watch = useMutation({
    mutationFn: (on: boolean) => api.updateLibrary(library.id, { watch: on }),
    onSuccess: refresh,
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" sx={{ alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
          <Typography variant="h6">{library.name}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
            {library.root_path}
          </Typography>
        </Stack>
        <Stack direction="row" sx={{ mt: 1, gap: 1, flexWrap: "wrap" }}>
          <Chip size="small" label={`${formatCount(library.image_count)} images`} />
          <Chip size="small" label={formatBytes(library.total_bytes)} />
          {library.error_count > 0 && (
            <Chip size="small" color="warning" clickable component={Link} href={`/libraries/${library.id}/errors`}
                  label={`${formatCount(library.error_count)} unreadable`} />
          )}
          <Chip size="small" variant="outlined" label={`Scanned: ${formatTimestamp(library.last_scan_at)}`} />
        </Stack>

        {running && current && <ScanProgress job={current} onCancel={() => api.cancelJob(current.id)} />}
        {running && !current && <LinearProgress sx={{ mt: 2 }} />}
        {!running && lastJob?.status === "failed" && (
          <Alert severity="error" sx={{ mt: 2 }}>Scan failed: {lastJob.message}</Alert>
        )}
        {!running && lastJob && lastJob.status !== "failed" && (
          <Alert severity={lastJob.status === "cancelled" ? "info" : "success"} sx={{ mt: 2 }}>
            Scan {lastJob.status}: {formatCount(lastJob.done)} processed
            {lastJob.elapsed_s && lastJob.done
              ? ` in ${lastJob.elapsed_s.toFixed(0)} s (${(lastJob.done / lastJob.elapsed_s).toFixed(0)} images/s)`
              : ""}
            {lastJob.failed ? `, ${lastJob.failed} unreadable` : ""}
            {lastJob.message ? `, ${lastJob.message}` : ""}.
          </Alert>
        )}
        {(scan.error || remove.error || watch.error) && (
          <Alert severity="error" sx={{ mt: 2 }}>{(scan.error ?? remove.error ?? watch.error)?.message}</Alert>
        )}
      </CardContent>
      <CardActions>
        <Button component={Link} href={`/libraries/${library.id}`}>Browse</Button>
        <Button component={Link} href={`/duplicates?library=${library.id}`}>Duplicates</Button>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title={library.watch_unavailable ?? "Rescan automatically a few seconds after files change"}>
          {/* span: a disabled control doesn't fire the events Tooltip needs */}
          <span>
            <FormControlLabel
              label="Watch"
              disabled={!!library.watch_unavailable || watch.isPending}
              control={<Switch size="small" checked={library.watch} onChange={(e) => watch.mutate(e.target.checked)} />}
            />
          </span>
        </Tooltip>
        <Button onClick={() => scan.mutate(false)} disabled={running} loading={scan.isPending}>
          Rescan
        </Button>
        <Button color="error" onClick={() => setConfirmRemove(true)} disabled={running}>
          Remove
        </Button>
      </CardActions>

      <Dialog open={confirmRemove} onClose={() => setConfirmRemove(false)}>
        <DialogTitle>Remove “{library.name}”?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This forgets the library and its index. Your image files are not touched.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmRemove(false)}>Keep</Button>
          <Button color="error" onClick={() => { setConfirmRemove(false); remove.mutate(); }}>
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
