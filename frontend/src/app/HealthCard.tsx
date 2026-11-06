"use client";
import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" sx={{ justifyContent: "space-between", py: 0.5 }}>
      <Typography color="text.secondary">{label}</Typography>
      <Typography component="div">{value}</Typography>
    </Stack>
  );
}

export default function HealthCard() {
  const { data, error, isPending } = useQuery({ queryKey: ["health"], queryFn: api.health });

  if (error) {
    return (
      <Alert severity="error">
        Backend unreachable. Start it with <code>uv run image-analyzer</code> in <code>backend/</code>.
      </Alert>
    );
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Backend
        </Typography>
        {isPending ? (
          <Stack spacing={1}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} height={28} />
            ))}
          </Stack>
        ) : (
          <>
            <Row label="Status" value={<Chip size="small" color="success" label={data.status} />} />
            <Row label="Version" value={data.version} />
            <Row label="Python" value={data.python} />
            <Row label="PyTorch" value={data.torch.version} />
            <Row
              label="GPU"
              value={
                data.torch.cuda_available ? (
                  <Chip size="small" color="success" label={data.torch.device} />
                ) : (
                  <Chip size="small" color="warning" label="CPU only" />
                )
              }
            />
            <Row
              label="Embeddings"
              value={
                data.embedder.error ? (
                  <Chip size="small" color="error" label="failed to load" title={data.embedder.error} />
                ) : data.embedder.name ? (
                  `${data.embedder.name} (${data.embedder.device})`
                ) : data.embedder.configured === "none" ? (
                  "disabled"
                ) : (
                  `${data.embedder.configured} (loads on first scan)`
                )
              }
            />
            <Row label="Data dir" value={<code>{data.data_dir}</code>} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
