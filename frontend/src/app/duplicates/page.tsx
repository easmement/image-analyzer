import { Suspense } from "react";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DuplicatesView from "./DuplicatesView";

function Fallback() {
  return (
    <Stack spacing={2}>
      <Skeleton variant="rounded" height={40} width={280} />
      <Skeleton variant="rounded" height={160} />
      <Skeleton variant="rounded" height={160} />
    </Stack>
  );
}

export default function DuplicatesPage() {
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Duplicates
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Exact copies, near-duplicates (resized, re-saved, edited, rotated) or similar images (burst
        shots, the same scene). The suggested copy to keep is outlined in green. Nothing is deleted;
        export the list to act on it yourself.
      </Typography>
      {/* DuplicatesView reads ?library= with useSearchParams, which needs a Suspense boundary. */}
      <Suspense fallback={<Fallback />}>
        <DuplicatesView />
      </Suspense>
    </Container>
  );
}
