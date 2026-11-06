import Chip, { type ChipProps } from "@mui/material/Chip";
import type { Match } from "@/lib/api";

const STYLE: Record<Match["verdict"], { label: string; color: ChipProps["color"] }> = {
  exact: { label: "Exact", color: "success" },
  near_duplicate: { label: "Near-duplicate", color: "primary" },
  similar: { label: "Similar", color: "secondary" },
  different: { label: "Different", color: "default" },
};

export default function VerdictChip({ verdict }: { verdict: Match["verdict"] }) {
  const { label, color } = STYLE[verdict];
  return <Chip size="small" color={color} label={label} variant={verdict === "different" ? "outlined" : "filled"} />;
}
