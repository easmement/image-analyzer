import { Suspense } from "react";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import ImageDetail from "./ImageDetail";

// params is runtime data under cacheComponents, so it's read inside a Suspense boundary.
export default function ImagePage({ params }: PageProps<"/images/[id]">) {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Suspense fallback={<Skeleton variant="rounded" height={480} />}>
        <ImageDetail params={params} />
      </Suspense>
    </Container>
  );
}
