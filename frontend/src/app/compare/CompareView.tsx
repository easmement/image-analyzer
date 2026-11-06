"use client";
import { useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import MuiLink from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "@/components/Link";
import VerdictChip from "@/components/VerdictChip";
import { api, type CompareResult, type ImageInfo, urls } from "@/lib/api";
import { formatBytes } from "@/lib/format";

type View = "side" | "swipe" | "diff";

/** Both aligned images stacked; B is revealed right of a draggable divider. */
function Swipe({ a, b, width, height }: { a: string; b: string; width: number; height: number }) {
  const [pos, setPos] = useState(50);
  const frame = useRef<HTMLDivElement>(null);
  const moveTo = (clientX: number) => {
    const rect = frame.current?.getBoundingClientRect();
    if (rect) setPos(Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100)));
  };
  return (
    <Box
      ref={frame}
      role="slider"
      aria-label="Swipe between A and B"
      aria-valuenow={Math.round(pos)}
      aria-valuemin={0}
      aria-valuemax={100}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 5));
        if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + 5));
      }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        moveTo(e.clientX);
      }}
      onPointerMove={(e) => e.buttons === 1 && moveTo(e.clientX)}
      sx={{ position: "relative", width: "100%", maxHeight: "75vh", aspectRatio: `${width} / ${height}`,
            cursor: "ew-resize", userSelect: "none", touchAction: "none", borderRadius: 1, overflow: "hidden",
            "&:focus-visible": { outline: 2, outlineColor: "primary.main" } }}
    >
      <Box component="img" src={a} alt="A" draggable={false}
           sx={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
      <Box component="img" src={b} alt="B" draggable={false}
           sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", clipPath: `inset(0 0 0 ${pos}%)` }} />
      <Box sx={{ position: "absolute", top: 0, bottom: 0, left: `${pos}%`, width: 2, ml: "-1px", bgcolor: "common.white",
                 boxShadow: 2 }} />
      {(["A", "B"] as const).map((label) => (
        <Typography key={label} variant="caption"
          sx={{ position: "absolute", top: 8, [label === "A" ? "left" : "right"]: 8, px: 1, borderRadius: 1,
                bgcolor: "rgba(0,0,0,0.6)", color: "common.white" }}>
          {label}
        </Typography>
      ))}
    </Box>
  );
}

function ImageHeader({ label, image }: { label: string; image: ImageInfo }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="overline" color="text.secondary">{label}</Typography>
      <MuiLink component={Link} href={`/images/${image.id}`} sx={{ display: "block", wordBreak: "break-all" }}>
        {image.rel_path}
      </MuiLink>
      <Typography variant="body2" color="text.secondary">
        {image.width}×{image.height} · {image.format} · {formatBytes(image.size_bytes)}
      </Typography>
    </Box>
  );
}

function Scores({ r }: { r: CompareResult }) {
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
  const rows: [string, React.ReactNode, string][] = [
    ["Verdict", r.verdict ? <VerdictChip verdict={r.verdict} /> : "not hashed yet", "From classify()"],
    ["Byte-identical", r.same_sha ? "yes" : "no", "Same SHA-256"],
    ["pHash distance", r.phash_distance ?? "—", "0–64, lower is closer; best orientation"],
    ["dHash distance", r.dhash_distance ?? "—", "0–64, at that same orientation"],
    ["Embedding cosine", r.cosine?.toFixed(3) ?? "—", "−1–1, higher is more alike in content"],
    ["SSIM", r.ssim.toFixed(3), "Structural similarity after alignment; 1 = identical"],
    ["Changed area", pct(r.changed_fraction), "Share of the frame that visibly differs"],
    ["Alignment", r.aligned_orientation_label, `B was transformed this way, then resized to ${r.width}×${r.height}`],
  ];
  return (
    <Table size="small">
      <TableBody>
        {rows.map(([label, value, hint]) => (
          <TableRow key={label}>
            <TableCell component="th" scope="row" sx={{ whiteSpace: "nowrap" }}>{label}</TableCell>
            <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{value}</TableCell>
            <TableCell sx={{ color: "text.secondary", display: { xs: "none", lg: "table-cell" } }}>{hint}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function CompareView() {
  const router = useRouter();
  const params = useSearchParams();
  const a = Number(params.get("a"));
  const b = Number(params.get("b"));
  const [view, setView] = useState<View>("swipe");
  const valid = Number.isInteger(a) && Number.isInteger(b) && a > 0 && b > 0;

  const result = useQuery({ queryKey: ["compare", a, b], queryFn: () => api.compare(a, b), enabled: valid });

  if (!valid) {
    return (
      <Alert severity="info">
        Pick two images to compare: use <strong>Compare</strong> on an image’s matches, or on a duplicate group.
      </Alert>
    );
  }
  if (result.error) return <Alert severity="error">{result.error.message}</Alert>;
  if (!result.data) return <Skeleton variant="rounded" height={520} />;
  const r = result.data;
  const src = (kind: "a" | "b" | "heatmap") => urls.compareImage(a, b, kind);

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", md: "row" }} sx={{ gap: 2, alignItems: { md: "flex-end" } }}>
        <ImageHeader label="A" image={r.a} />
        <Button startIcon={<SwapHorizIcon />} onClick={() => router.replace(urls.compare(b, a))} sx={{ flexShrink: 0 }}>
          Swap
        </Button>
        <ImageHeader label="B" image={r.b} />
      </Stack>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)}
                             aria-label="Comparison view" sx={{ mb: 2 }}>
            <ToggleButton value="side">Side by side</ToggleButton>
            <ToggleButton value="swipe">Swipe</ToggleButton>
            <ToggleButton value="diff">Differences</ToggleButton>
          </ToggleButtonGroup>

          {view === "side" && (
            <Grid container spacing={1}>
              {(["a", "b"] as const).map((k) => (
                <Grid key={k} size={6}>
                  <Box component="img" src={src(k)} alt={k.toUpperCase()}
                       sx={{ width: "100%", maxHeight: "70vh", objectFit: "contain", borderRadius: 1 }} />
                </Grid>
              ))}
            </Grid>
          )}
          {view === "swipe" && <Swipe a={src("a")} b={src("b")} width={r.width} height={r.height} />}
          {view === "diff" && (
            <Box sx={{ position: "relative", width: "100%", maxHeight: "75vh", aspectRatio: `${r.width} / ${r.height}`,
                       borderRadius: 1, overflow: "hidden" }}>
              {/* A in muted grey, so the red difference overlay stands out */}
              <Box component="img" src={src("a")} alt="A"
                   sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", filter: "grayscale(1) opacity(0.6)" }} />
              <Box component="img" src={src("heatmap")} alt="Differences between A and B"
                   sx={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
            </Box>
          )}
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" component="h2" gutterBottom>Scores</Typography>
              <Scores r={r} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
}
