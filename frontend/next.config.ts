import type { NextConfig } from "next";

const backend = process.env.IMAGE_ANALYZER_API ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Same-origin proxy to the FastAPI backend: no CORS, and the backend stays on localhost.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
