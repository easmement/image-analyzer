import { Suspense } from "react";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import ErrorsView from "./ErrorsView";

// params is runtime data under cacheComponents, so it's read inside a Suspense boundary.
export default function ErrorsPage({ params }: PageProps<"/libraries/[id]/errors">) {
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Suspense fallback={<Skeleton variant="rounded" height={320} />}>
        <ErrorsView params={params} />
      </Suspense>
    </Container>
  );
}
