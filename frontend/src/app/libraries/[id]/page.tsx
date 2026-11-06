import { Suspense } from "react";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import Gallery from "./Gallery";

// params is runtime data under cacheComponents, so it's read inside a Suspense boundary.
export default function LibraryPage({ params }: PageProps<"/libraries/[id]">) {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Suspense fallback={<Skeleton variant="text" width={300} height={48} />}>
        <Gallery params={params} />
      </Suspense>
    </Container>
  );
}
