"use client";
import { Suspense } from "react";
import AppBar from "@mui/material/AppBar";
import Button from "@mui/material/Button";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import { usePathname } from "next/navigation";
import Link from "./Link";

const LINKS = [
  { href: "/", label: "Libraries" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/search", label: "Search" },
  { href: "/settings", label: "Settings" },
];

function isActive(href: string, pathname: string | null) {
  if (!pathname) return false;
  return href === "/" ? pathname === "/" || pathname.startsWith("/libraries") : pathname.startsWith(href);
}

function NavLinks({ pathname }: { pathname: string | null }) {
  return LINKS.map(({ href, label }) => {
    const active = isActive(href, pathname);
    return (
      <Button key={href} component={Link} href={href} color={active ? "primary" : "inherit"}
              aria-current={active ? "page" : undefined}>
        {label}
      </Button>
    );
  });
}

// usePathname() is runtime data under cacheComponents; reading it inside Suspense keeps the
// rest of every page prerenderable. The fallback renders the same buttons, so nothing shifts.
function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

export default function NavBar() {
  return (
    <AppBar position="sticky" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
      <Toolbar sx={{ gap: 1 }}>
        <ImageSearchIcon color="primary" />
        <Typography variant="h6" component={Link} href="/" sx={{ mr: 3, color: "inherit", textDecoration: "none" }}>
          Image Analyzer
        </Typography>
        <Suspense fallback={<NavLinks pathname={null} />}>
          <ActiveNavLinks />
        </Suspense>
      </Toolbar>
    </AppBar>
  );
}
