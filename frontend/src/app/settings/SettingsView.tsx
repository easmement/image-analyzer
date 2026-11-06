"use client";
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ThresholdSettings } from "@/lib/api";

const FIELDS: { key: keyof ThresholdSettings; label: string; help: string; min: number; max: number; step: number }[] = [
  { key: "near_phash", label: "Near-duplicate: max pHash distance", help: "Higher catches more edits and crops, and more unrelated look-alikes.", min: 0, max: 20, step: 1 },
  { key: "near_dhash", label: "Near-duplicate: max dHash distance", help: "Must also hold; filters coincidental pHash matches, especially rotated ones.", min: 0, max: 64, step: 1 },
  { key: "similar_cosine", label: "Similar: min embedding cosine", help: "Lower groups more of the same scene, and more unrelated photos.", min: 0.5, max: 1, step: 0.01 },
];

/** Editing form; mounted with the saved values, and remounted (via key) when they change. */
function ThresholdsForm({ saved, defaults }: { saved: ThresholdSettings; defaults: ThresholdSettings }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ThresholdSettings>(saved);
  const save = useMutation({
    mutationFn: (t: ThresholdSettings) => api.setThresholds(t),
    onSuccess: (s) => {
      queryClient.setQueryData(["settings"], s);
      // Verdicts are computed on every request, so cached matches and groups are now stale.
      for (const key of ["similar", "groups", "compare"]) queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
  const dirty = FIELDS.some((f) => draft[f.key] !== saved[f.key]);
  const isDefault = FIELDS.every((f) => draft[f.key] === defaults[f.key]);

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" component="h2">Match thresholds</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Applied immediately to matches and duplicate groups; no rescan needed. Check a change with{" "}
          <code>make eval</code>, which uses the same saved values.
        </Typography>
        <Stack spacing={3}>
          {FIELDS.map((f) => (
            <Box key={f.key}>
              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <Typography id={`${f.key}-label`}>{f.label}</Typography>
                <Typography sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 500 }}>
                  {f.step < 1 ? draft[f.key].toFixed(2) : draft[f.key]}
                  {draft[f.key] !== defaults[f.key] && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {" "}(default {defaults[f.key]})
                    </Typography>
                  )}
                </Typography>
              </Stack>
              <Slider aria-labelledby={`${f.key}-label`} min={f.min} max={f.max} step={f.step}
                      value={draft[f.key]} onChange={(_, v) => setDraft({ ...draft, [f.key]: v as number })} />
              <Typography variant="caption" color="text.secondary">{f.help}</Typography>
            </Box>
          ))}
        </Stack>
        {save.error && <Alert severity="error" sx={{ mt: 2 }}>{save.error.message}</Alert>}
        {save.isSuccess && !dirty && <Alert severity="success" sx={{ mt: 2 }}>Saved.</Alert>}
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Button variant="contained" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(draft)}>
          Save
        </Button>
        <Button disabled={!dirty} onClick={() => setDraft(saved)}>Discard changes</Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button disabled={isDefault} onClick={() => setDraft(defaults)}>Restore defaults</Button>
      </CardActions>
    </Card>
  );
}

export default function SettingsView() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  if (settings.error) return <Alert severity="error">{settings.error.message}</Alert>;
  if (!settings.data) return <Skeleton variant="rounded" height={420} />;
  const { thresholds, defaults, config } = settings.data;

  return (
    <Stack spacing={3}>
      <ThresholdsForm key={JSON.stringify(thresholds)} saved={thresholds} defaults={defaults} />
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" component="h2">Configuration</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Set with <code>IMAGE_ANALYZER_*</code> environment variables (for example{" "}
            <code>IMAGE_ANALYZER_DATA_DIR</code>, <code>IMAGE_ANALYZER_WORKERS</code>,{" "}
            <code>IMAGE_ANALYZER_EMBEDDER</code>) and applied when the backend restarts.
          </Typography>
          <Table size="small">
            <TableBody>
              {Object.entries(config).map(([key, value]) => (
                <TableRow key={key}>
                  <TableCell component="th" scope="row" sx={{ fontFamily: "monospace" }}>{key}</TableCell>
                  <TableCell sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                    {value === null ? "—" : String(value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  );
}
