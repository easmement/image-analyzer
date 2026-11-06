"use client";
import { use, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import MuiLink from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import ReplayIcon from "@mui/icons-material/Replay";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "@/components/Link";
import { useJobEvents } from "@/hooks/useJobEvents";
import { api, type Job } from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";

export default function ErrorsView({ params }: { params: Promise<{ id: string }> }) {
  const libraryId = Number(use(params).id);
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastRetry, setLastRetry] = useState<Job | null>(null);

  const library = useQuery({ queryKey: ["library", libraryId], queryFn: () => api.library(libraryId) });
  const report = useQuery({ queryKey: ["errors", libraryId], queryFn: () => api.errors(libraryId) });

  const job = useJobEvents(jobId, (done) => {
    setJobId(null);
    setLastRetry(done);
    queryClient.invalidateQueries({ queryKey: ["errors", libraryId] });
    queryClient.invalidateQueries({ queryKey: ["libraries"] });
    queryClient.invalidateQueries({ queryKey: ["library", libraryId] });
  });
  const retry = useMutation({
    mutationFn: () => api.startScan(libraryId, { retryErrors: true }),
    onSuccess: (started) => {
      setLastRetry(null);
      setJobId(started.id);
    },
  });

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <MuiLink component={Link} href="/" underline="hover" color="inherit">Libraries</MuiLink>
        <MuiLink component={Link} href={`/libraries/${libraryId}`} underline="hover" color="inherit">
          {library.data?.name ?? "Library"}
        </MuiLink>
        <Typography color="text.primary">Unreadable files</Typography>
      </Breadcrumbs>

      <Stack direction={{ xs: "column", sm: "row" }} sx={{ gap: 2, alignItems: { sm: "center" } }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h4" component="h1">Unreadable files</Typography>
          <Typography color="text.secondary">
            Files the scanner couldn’t decode. They’re skipped, not deleted, and retried automatically
            when they change. Fixed one in place? Retry now.
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<ReplayIcon />} onClick={() => retry.mutate()}
                loading={retry.isPending || !!jobId} disabled={!report.data?.total}>
          Retry unreadable files
        </Button>
      </Stack>

      {jobId && <LinearProgress variant={job?.total ? "determinate" : "indeterminate"}
                                value={job?.total ? (job.done / job.total) * 100 : 0} />}
      {lastRetry && (
        <Alert severity={lastRetry.status === "completed" ? "success" : "warning"}>
          Retry {lastRetry.status}: {formatCount(lastRetry.done - lastRetry.failed)} now readable,{" "}
          {formatCount(lastRetry.failed)} still failing.
        </Alert>
      )}
      {(report.error || retry.error) && <Alert severity="error">{(report.error ?? retry.error)?.message}</Alert>}
      {report.isPending && <Skeleton variant="rounded" height={240} />}
      {report.data?.total === 0 && <Alert severity="success">Every file in this library was read successfully.</Alert>}

      {report.data && report.data.total > 0 && (
        <>
          <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
            {report.data.kinds.map((k) => (
              <Chip key={k.kind} color="warning" variant="outlined" title={k.example}
                    label={`${k.kind} · ${formatCount(k.count)}`} />
            ))}
          </Stack>
          <TableContainer component={Card} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell>Error</TableCell>
                  <TableCell align="right">Size</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {report.data.items.map((img) => (
                  <TableRow key={img.id}>
                    <TableCell sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>{img.rel_path}</TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{img.error}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatBytes(img.size_bytes)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Stack>
  );
}
