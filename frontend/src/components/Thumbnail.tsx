"use client";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import BrokenImageIcon from "@mui/icons-material/BrokenImageOutlined";
import { type ImageInfo, urls } from "@/lib/api";

/** Square thumbnail tile. Unreadable images show an icon with the error as a tooltip. */
export default function Thumbnail({ image, size, highlight }: { image: ImageInfo; size?: number; highlight?: boolean }) {
  const name = image.rel_path.split("/").pop();
  return (
    <Box
      sx={{
        width: size ?? "100%",
        aspectRatio: "1",
        borderRadius: 1,
        overflow: "hidden",
        bgcolor: "action.hover",
        outline: highlight ? 3 : 0,
        outlineColor: "success.main",
        outlineOffset: -3,
        display: "grid",
        placeItems: "center",
      }}
    >
      {image.status === "ok" && image.sha256 ? (
        <img
          src={urls.thumbnail(image)}
          alt={name}
          loading="lazy"
          decoding="async"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <Tooltip title={image.error ?? "Unreadable"}>
          <BrokenImageIcon color="disabled" fontSize="large" aria-label={`Unreadable: ${image.error}`} />
        </Tooltip>
      )}
    </Box>
  );
}
