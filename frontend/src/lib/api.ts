import type { components } from "./types.gen";

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type Library = Schemas["Library"];
export type LibraryCreate = Schemas["LibraryCreate"];
export type Job = Schemas["Job"];
export type ImageInfo = Schemas["ImageInfo"];
export type ImagePage = Schemas["ImagePage"];
export type DuplicateGroup = Schemas["DuplicateGroup"];
export type Match = Schemas["Match"];
export type GroupLevel = DuplicateGroup["level"];
export type CompareResult = Schemas["CompareResult"];
export type SearchResult = Schemas["SearchResult"];
export type ErrorReport = Schemas["ErrorReport"];
export type AppSettings = Schemas["AppSettings"];
export type ThresholdSettings = Schemas["ThresholdSettings"];
export type LibraryUpdate = Schemas["LibraryUpdate"];

export const TERMINAL_STATUSES: Job["status"][] = ["completed", "cancelled", "failed"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers:
      typeof init?.body === "string" ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    // FastAPI errors look like {"detail": "..."} (or a list of validation errors).
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

function query(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export const api = {
  health: () => request<Health>("/api/health"),

  libraries: () => request<Library[]>("/api/libraries"),
  library: (id: number) => request<Library>(`/api/libraries/${id}`),
  createLibrary: (body: LibraryCreate) =>
    request<Library>("/api/libraries", { method: "POST", body: JSON.stringify(body) }),
  deleteLibrary: (id: number) => request<void>(`/api/libraries/${id}`, { method: "DELETE" }),
  updateLibrary: (id: number, body: LibraryUpdate) =>
    request<Library>(`/api/libraries/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  startScan: (id: number, opts: { full?: boolean; retryErrors?: boolean } = {}) =>
    request<Job>(
      `/api/libraries/${id}/scan${query({ full: opts.full ? "true" : undefined, retry_errors: opts.retryErrors ? "true" : undefined })}`,
      { method: "POST" },
    ),
  errors: (id: number) => request<ErrorReport>(`/api/libraries/${id}/errors`),
  settings: () => request<AppSettings>("/api/settings"),
  setThresholds: (t: ThresholdSettings) =>
    request<AppSettings>("/api/settings/thresholds", { method: "PUT", body: JSON.stringify(t) }),

  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}`, { method: "DELETE" }),

  images: (p: { libraryId: number; cursor?: string | null; status?: "ok" | "error"; limit?: number }) =>
    request<ImagePage>(
      `/api/images${query({ library_id: p.libraryId, cursor: p.cursor, status: p.status, limit: p.limit })}`,
    ),
  image: (id: number) => request<ImageInfo>(`/api/images/${id}`),
  similar: (id: number, p: { method?: "perceptual" | "semantic"; minCosine?: number; limit?: number } = {}) =>
    request<Match[]>(
      `/api/images/${id}/similar${query({ method: p.method, min_cosine: p.minCosine, limit: p.limit ?? 48 })}`,
    ),
  compare: (a: number, b: number) => request<CompareResult>(`/api/compare${query({ a, b })}`),
  searchImage: (file: File, libraryId?: number) => {
    const form = new FormData(); // the browser sets the multipart Content-Type and boundary
    form.append("file", file);
    if (libraryId !== undefined) form.append("library_id", String(libraryId));
    return request<SearchResult>("/api/search/image", { method: "POST", body: form });
  },
  groups: (libraryId?: number, level: GroupLevel = "exact") =>
    request<DuplicateGroup[]>(`/api/groups${query({ library_id: libraryId, level })}`),
};

export const urls = {
  jobEvents: (jobId: string) => `/api/jobs/${jobId}/events`,
  // ?v= makes the URL change whenever the content does, so the browser can cache it forever.
  thumbnail: (img: Pick<ImageInfo, "id" | "sha256">) => `/api/images/${img.id}/thumbnail?v=${img.sha256}`,
  file: (img: Pick<ImageInfo, "id">) => `/api/images/${img.id}/file`,
  compareImage: (a: number, b: number, kind: "a" | "b" | "heatmap") => `/api/compare/image${query({ a, b, kind })}`,
  compare: (a: number, b: number) => `/compare?a=${a}&b=${b}`,
  groupsCsv: (libraryId?: number, level: GroupLevel = "exact") =>
    `/api/groups/export${query({ library_id: libraryId, level })}`,
};
