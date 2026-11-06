const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(unit === 0 || value >= 100 ? 0 : 1)} ${UNITS[unit]}`;
}

export function formatCount(n: number): string {
  return n.toLocaleString();
}

/** SQLite's datetime('now') is UTC without a zone marker; show it in local time. */
export function formatTimestamp(sqliteUtc: string | null | undefined): string {
  if (!sqliteUtc) return "never";
  return new Date(`${sqliteUtc.replace(" ", "T")}Z`).toLocaleString();
}
