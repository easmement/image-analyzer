"use client";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardActions from "@mui/material/CardActions";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CompareIcon from "@mui/icons-material/Compare";
import { type Match, urls } from "@/lib/api";
import Link from "./Link";
import Thumbnail from "./Thumbnail";
import VerdictChip from "./VerdictChip";

/** A match with its verdict and scores. With compareWith, adds a Compare action for that pair. */
export default function MatchCard({ match, compareWith }: { match: Match; compareWith?: number }) {
  const { image } = match;
  return (
    <Card variant="outlined">
      <CardActionArea component={Link} href={`/images/${image.id}`} sx={{ p: 1 }}>
        <Thumbnail image={image} />
        <Stack direction="row" sx={{ mt: 1, gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
          <VerdictChip verdict={match.verdict} />
          {match.orientation !== 0 && (
            <Typography variant="caption" color="text.secondary">{match.orientation_label}</Typography>
          )}
        </Stack>
        <Typography variant="caption" component="div" noWrap title={image.rel_path} sx={{ mt: 0.5 }}>
          {image.rel_path}
        </Typography>
        <Typography variant="caption" component="div" color="text.secondary">
          pHash {match.phash_distance} · dHash {match.dhash_distance}
          {match.cosine !== null && ` · cos ${match.cosine.toFixed(2)}`}
        </Typography>
      </CardActionArea>
      {compareWith !== undefined && (
        <CardActions sx={{ pt: 0 }}>
          <Button size="small" startIcon={<CompareIcon />} component={Link} href={urls.compare(compareWith, image.id)}>
            Compare
          </Button>
        </CardActions>
      )}
    </Card>
  );
}
