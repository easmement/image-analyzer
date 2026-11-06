"use client";
import { createTheme } from "@mui/material/styles";

// Light and dark palettes, switched by the OS setting via a CSS media query.
const theme = createTheme({
  cssVariables: true,
  colorSchemes: { light: true, dark: true },
});

export default theme;
