"use client";
import { use, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { styled } from "@mui/material/styles";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { VirtuosoGrid } from "react-virtuoso";
import Link from "@/components/Link";
import Thumbnail from "@/components/Thumbnail";
import { api } from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";

const PAGE_SIZE = 200;

// styled() components forward refs, which VirtuosoGrid needs to measure items.
const GridList = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
  gap: theme.spacing(1.5),
}));
const GridItem = styled("div")({ minWidth: 0 });

export default function Gallery({ params }: { params: Promise<{ id: string }> }) {
  const libraryId = Number(use(params).id);
  const [filter, setFilter] = useState<"all" | "error">("all");

  const library = useQuery({ queryKey: ["library", libraryId], queryFn: () => api.library(libraryId) });
  const images = useInfiniteQuery({
    queryKey: ["images", libraryId, filter],
    queryFn: ({ pageParam }) =>
      api.images({ libraryId, cursor: pageParam, limit: PAGE_SIZE, status: filter === "error" ? "error" : undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const items = images.data?.pages.flatMap((p) => p.items) ?? [];

  if (library.error) {
    return <Alert severity="error">{library.error.message}</Alert>;
  }

  return (
    <>
      <Stack direction={{ xs: "column", sm: "row" }} sx={{ mb: 3, gap: 2, alignItems: { sm: "flex-end" } }}>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography variant="h4" component="h1">
            {library.data?.name ?? "…"}
          </Typography>
          {library.data && (
            <Typography color="text.secondary" noWrap>
              {formatCount(library.data.image_count)} images · {formatBytes(library.data.total_bytes)} ·{" "}
              <Box component="span" sx={{ fontFamily: "monospace" }}>{library.data.root_path}</Box>
            </Typography>
          )}
        </Box>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filter}
          onChange={(_, value) => value && setFilter(value)}
          aria-label="Filter images"
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="error" disabled={!library.data?.error_count}>
            Unreadable ({library.data?.error_count ?? 0})
          </ToggleButton>
        </ToggleButtonGroup>
        <Button component={Link} href={`/duplicates?library=${libraryId}`} variant="outlined">
          Duplicates
        </Button>
      </Stack>

      {images.error && <Alert severity="error">{images.error.message}</Alert>}
      {images.isSuccess && items.length === 0 && (
        <Typography color="text.secondary">
          No images yet. Run a scan from the Libraries page.
        </Typography>
      )}

      <VirtuosoGrid
        useWindowScroll
        data={items}
        components={{ List: GridList, Item: GridItem }}
        endReached={() => images.hasNextPage && !images.isFetchingNextPage && images.fetchNextPage()}
        increaseViewportBy={600}
        itemContent={(_, image) => (
          <Box
            component={Link}
            href={`/images/${image.id}`}
            title={image.rel_path}
            sx={{ display: "block", color: "inherit", textDecoration: "none" }}
          >
            <Thumbnail image={image} />
            <Typography variant="caption" component="div" noWrap sx={{ mt: 0.5 }}>
              {image.rel_path.split("/").pop()}
            </Typography>
            <Typography variant="caption" component="div" color="text.secondary" noWrap>
              {image.width && image.height ? `${image.width}×${image.height} · ` : ""}
              {formatBytes(image.size_bytes)}
            </Typography>
          </Box>
        )}
      />
    </>
  );
}
