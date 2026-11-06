"use client";
// Next.js 16 can't pass next/link as a `component` prop from a Server Component, so MUI
// components use this client re-export instead (see MUI's Next.js integration guide).
import Link from "next/link";

export default Link;
