"use client";
import { use, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import MuiLink from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import Link from "@/components/Link";
import MatchCard from "@/components/MatchCard";
import { api, urls } from "@/lib/api";
import { formatBytes } from "@/lib/format";

export default function ImageDetail({ params }: { params: Promise<{ id: string }> }) {
  const imageId = Number(use(params).id);
  const [showWeak, setShowWeak] = useState(false);
  const [method, setMethod] = useState<"perceptual" | "semantic">("perceptual");
  // The slider shows its value live but only re-queries when released.
  const [minCosine, setMinCosine] = useState(0.75);
  const [sliderValue, setSliderValue] = useState(0.75);

  const image = useQuery({ queryKey: ["image", imageId], queryFn: () => api.image(imageId) });
  const library = useQuery({
    queryKey: ["library", image.data?.library_id],
    queryFn: () => api.library(image.data!.library_id),
    enabled: !!image.data,
  });
  const matches = useQuery({
    queryKey: ["similar", imageId, method, method === "semantic" ? minCosine : null],
    queryFn: () => api.similar(imageId, { method, minCosine: method === "semantic" ? minCosine : undefined }),
    placeholderData: (previous) => previous, // keep the old strip visible while the slider re-queries
  });

  if (image.error) return <Alert severity="error">{image.error.message}</Alert>;
  if (!image.data) return <Skeleton variant="rounded" height={480} />;
  const img = image.data;

  const visible = matches.data?.filter((m) => showWeak || m.verdict !== "different") ?? [];
  const hidden = (matches.data?.length ?? 0) - visible.length;

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <MuiLink component={Link} href="/" underline="hover" color="inherit">Libraries</MuiLink>
        <MuiLink component={Link} href={`/libraries/${img.library_id}`} underline="hover" color="inherit">
          {library.data?.name ?? "Library"}
        </MuiLink>
        <Typography color="text.primary" sx={{ wordBreak: "break-all" }}>{img.rel_path}</Typography>
      </Breadcrumbs>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          {img.status === "ok" ? (
            <Box
              component="img"
              src={urls.file(img)}
              alt={img.rel_path}
              sx={{ width: "100%", maxHeight: "70vh", objectFit: "contain", bgcolor: "action.hover", borderRadius: 1 }}
            />
          ) : (
            <Alert severity="warning">This file couldn’t be read: {img.error}</Alert>
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Stack spacing={1}>
            {[
              ["Dimensions", img.width && img.height ? `${img.width} × ${img.height}` : "—"],
              ["Format", img.format ?? "—"],
              ["Size", formatBytes(img.size_bytes)],
              ["SHA-256", <Box key="sha" component="span" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>{img.sha256}</Box>],
            ].map(([label, value]) => (
              <Box key={label as string}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography>{value}</Typography>
              </Box>
            ))}
            <MuiLink href={urls.file(img)} target="_blank" rel="noopener">Open original</MuiLink>
          </Stack>
        </Grid>
      </Grid>

      <Box>
        <Stack direction="row" sx={{ mb: 2, alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>
            Matches
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={method}
            onChange={(_, v) => v && setMethod(v)}
            aria-label="Match type"
          >
            <ToggleButton value="perceptual">Near-duplicates</ToggleButton>
            <ToggleButton value="semantic">Similar</ToggleButton>
          </ToggleButtonGroup>
          {method === "semantic" && (
            <Stack direction="row" sx={{ alignItems: "center", gap: 1.5, minWidth: 260 }}>
              <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                Min similarity
              </Typography>
              <Slider
                size="small"
                min={0.5}
                max={1}
                step={0.01}
                value={sliderValue}
                onChange={(_, v) => setSliderValue(v as number)}
                onChangeCommitted={(_, v) => setMinCosine(v as number)}
                valueLabelDisplay="auto"
                aria-label="Minimum cosine similarity"
              />
              <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
                {sliderValue.toFixed(2)}
              </Typography>
            </Stack>
          )}
          <FormControlLabel
            control={<Switch checked={showWeak} onChange={(e) => setShowWeak(e.target.checked)} />}
            label={`Show weaker candidates${hidden && !showWeak ? ` (${hidden})` : ""}`}
          />
        </Stack>
        {matches.error && <Alert severity="error">{matches.error.message}</Alert>}
        {matches.isPending && <Skeleton variant="rounded" height={200} />}
        {matches.data && visible.length === 0 && (
          <Typography color="text.secondary">
            {method === "perceptual"
              ? "No duplicates or near-duplicates of this image."
              : "No similar images above this threshold. Try lowering it."}
          </Typography>
        )}
        <Grid container spacing={1.5}>
          {visible.map((m) => (
            <Grid key={m.image.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
              <MatchCard match={m} compareWith={imageId} />
            </Grid>
          ))}
        </Grid>
      </Box>
    </Stack>
  );
}
