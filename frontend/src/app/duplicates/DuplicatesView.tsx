"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import DownloadIcon from "@mui/icons-material/Download";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "@/components/Link";
import Thumbnail from "@/components/Thumbnail";
import { api, type DuplicateGroup, type GroupLevel, urls } from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";

function GroupCard({ group }: { group: DuplicateGroup }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" sx={{ mb: 2, gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
            {group.count} {{ exact: "copies", near_duplicate: "versions", similar: "similar images" }[group.level]}
          </Typography>
          <Chip size="small" color="primary" variant="outlined" label={`${formatBytes(group.reclaimable_bytes)} reclaimable`} />
          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
            {group.level === "exact" ? group.key.slice(0, 12) : ""}
          </Typography>
        </Stack>
        <Stack direction="row" sx={{ gap: 2, overflowX: "auto", pb: 1 }}>
          {group.images.map((img) => {
            const keep = img.id === group.best_id;
            return (
              // The picture and path are one link; the action sits beside it (links can't nest).
              <Box key={img.id} sx={{ width: 160, flexShrink: 0 }}>
                <Box component={Link} href={`/images/${img.id}`} sx={{ display: "block", color: "inherit", textDecoration: "none" }}>
                  <Thumbnail image={img} highlight={keep} />
                  <Typography variant="caption" component="div" title={img.rel_path} sx={{ mt: 0.5, wordBreak: "break-all" }}>
                    {img.rel_path}
                  </Typography>
                </Box>
                {keep ? (
                  <Chip size="small" color="success" label="Keep" sx={{ mt: 0.5 }} />
                ) : (
                  <Button size="small" component={Link} href={urls.compare(group.best_id, img.id)}
                          sx={{ mt: 0.5, px: 0.5, minWidth: 0 }}>
                    Compare with keeper
                  </Button>
                )}
              </Box>
            );
          })}
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function DuplicatesView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const libraryParam = searchParams.get("library");
  const libraryId = libraryParam ? Number(libraryParam) : undefined;
  const levelParam = searchParams.get("level");
  const level: GroupLevel = levelParam === "near_duplicate" || levelParam === "similar" ? levelParam : "exact";

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null) next.delete(key);
    else next.set(key, value);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  };

  const libraries = useQuery({ queryKey: ["libraries"], queryFn: api.libraries });
  const groups = useQuery({
    queryKey: ["groups", libraryId ?? "all", level],
    queryFn: () => api.groups(libraryId, level),
  });

  const totalReclaimable = groups.data?.reduce((sum, g) => sum + g.reclaimable_bytes, 0) ?? 0;

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} sx={{ gap: 2, alignItems: { sm: "center" } }}>
        <FormControl size="small" sx={{ minWidth: 240 }}>
          <InputLabel id="library-select">Library</InputLabel>
          <Select
            labelId="library-select"
            label="Library"
            value={libraryParam ?? "all"}
            onChange={(e) => setParam("library", e.target.value === "all" ? null : e.target.value)}
          >
            <MenuItem value="all">All libraries</MenuItem>
            {libraries.data?.map((l) => (
              <MenuItem key={l.id} value={String(l.id)}>{l.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={level}
          onChange={(_, v) => v && setParam("level", v === "exact" ? null : v)}
          aria-label="Match level"
        >
          <ToggleButton value="exact">Exact</ToggleButton>
          <ToggleButton value="near_duplicate">Near-duplicate</ToggleButton>
          <ToggleButton value="similar">Similar</ToggleButton>
        </ToggleButtonGroup>
        {groups.data && (
          <Typography color="text.secondary" sx={{ flexGrow: 1 }}>
            {formatCount(groups.data.length)} groups · {formatBytes(totalReclaimable)} reclaimable
          </Typography>
        )}
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          href={urls.groupsCsv(libraryId, level)}
          disabled={!groups.data?.length}
        >
          Export CSV
        </Button>
      </Stack>

      {groups.error && <Alert severity="error">{groups.error.message}</Alert>}
      {groups.isPending && [0, 1].map((i) => <Skeleton key={i} variant="rounded" height={220} />)}
      {groups.data?.length === 0 && (
        <Alert severity="success">
          No {{ exact: "exact duplicates", near_duplicate: "near-duplicates", similar: "similar images" }[level]} found.
        </Alert>
      )}
      {groups.data?.map((g) => <GroupCard key={g.key} group={g} />)}
    </Stack>
  );
}
