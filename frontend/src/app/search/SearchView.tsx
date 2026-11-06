"use client";
import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import InputLabel from "@mui/material/InputLabel";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import UploadIcon from "@mui/icons-material/FileUploadOutlined";
import { useMutation, useQuery } from "@tanstack/react-query";
import MatchCard from "@/components/MatchCard";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";

export default function SearchView() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [libraryId, setLibraryId] = useState<string>("all");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const libraries = useQuery({ queryKey: ["libraries"], queryFn: api.libraries });
  const search = useMutation({
    mutationFn: ({ f, lib }: { f: File; lib: string }) => api.searchImage(f, lib === "all" ? undefined : Number(lib)),
  });

  // The preview is a local object URL: made when a file is chosen, released when it's replaced
  // (in choose) or when the page unmounts (this effect's cleanup).
  const previewRef = useRef<string | null>(null);
  useEffect(() => () => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
  }, []);

  const choose = (f: File | undefined) => {
    if (!f) return;
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = URL.createObjectURL(f);
    setPreview(previewRef.current);
    setFile(f);
    search.mutate({ f, lib: libraryId });
  };

  const result = search.data;
  const visible = result?.matches.filter((m) => m.verdict !== "different") ?? [];

  return (
    <Stack spacing={3}>
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper
            variant="outlined"
            role="button"
            tabIndex={0}
            aria-label="Choose or drop an image"
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              choose(e.dataTransfer.files[0]);
            }}
            sx={{
              p: 2, minHeight: 240, display: "grid", placeItems: "center", cursor: "pointer", textAlign: "center",
              borderStyle: "dashed", borderWidth: 2, borderColor: dragging ? "primary.main" : "divider",
              bgcolor: dragging ? "action.hover" : "transparent",
              "&:focus-visible": { outline: 2, outlineColor: "primary.main" },
            }}
          >
            {preview ? (
              <Box component="img" src={preview} alt="Image being searched for"
                   sx={{ maxWidth: "100%", maxHeight: 320, objectFit: "contain", borderRadius: 1 }} />
            ) : (
              <Stack sx={{ alignItems: "center", gap: 1 }}>
                <UploadIcon color="action" sx={{ fontSize: 48 }} />
                <Typography>Drop an image here, or click to choose one</Typography>
                <Typography variant="body2" color="text.secondary">JPEG, PNG, WebP, GIF, BMP, TIFF · up to 50 MB</Typography>
              </Stack>
            )}
          </Paper>
          <input
            ref={input}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              choose(e.target.files?.[0]);
              e.target.value = ""; // so choosing the same file again still triggers a search
            }}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Stack spacing={2}>
            <FormControl size="small" sx={{ maxWidth: 320 }}>
              <InputLabel id="search-library">Search in</InputLabel>
              <Select
                labelId="search-library"
                label="Search in"
                value={libraryId}
                onChange={(e) => {
                  setLibraryId(e.target.value);
                  if (file) search.mutate({ f: file, lib: e.target.value });
                }}
              >
                <MenuItem value="all">All libraries</MenuItem>
                {libraries.data?.map((l) => (
                  <MenuItem key={l.id} value={String(l.id)}>{l.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
            {search.isPending && <LinearProgress />}
            {search.error && <Alert severity="error">{search.error.message}</Alert>}
            {result && (
              <Box>
                <Typography variant="subtitle1">{result.query.filename}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {result.query.width}×{result.query.height} · {result.query.format}
                  {file && ` · ${formatBytes(file.size)}`}
                </Typography>
                {!result.query.embedded && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    The embedding model isn’t available, so only near-duplicates can be found.
                  </Alert>
                )}
              </Box>
            )}
          </Stack>
        </Grid>
      </Grid>

      {result && (
        <Box>
          <Typography variant="h6" component="h2" sx={{ mb: 2 }}>
            {visible.length ? `${visible.length} matches` : "No matches"}
          </Typography>
          <Grid container spacing={1.5}>
            {visible.map((m) => (
              <Grid key={m.image.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                <MatchCard match={m} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}
    </Stack>
  );
}
