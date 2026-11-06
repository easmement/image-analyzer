import { Suspense } from "react";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import CompareView from "./CompareView";

export default function ComparePage() {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* CompareView reads ?a=&b= with useSearchParams, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton variant="rounded" height={520} />}>
        <CompareView />
      </Suspense>
    </Container>
  );
}
