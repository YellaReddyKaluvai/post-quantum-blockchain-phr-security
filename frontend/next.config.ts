import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: path.resolve(__dirname),
  },
  // Proxy API calls through this server instead of having the browser reach the
  // backend directly. Two reasons: the browser then talks to one origin, so no
  // CORS handling is needed; and when the app is exposed through a tunnel only
  // this port has to be published — the backend stays on loopback rather than
  // becoming a second thing on the public internet.
  async rewrites() {
    // Hosting platforms hand this over as a bare host ("api.example.com"),
    // while local development sets a full URL. Normalise rather than requiring
    // whoever configures the deployment to know which form is expected —
    // getting it wrong yields a rewrite to a relative path and every API call
    // 404s with nothing to explain why.
    const raw = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    const backend = /^https?:\/\//.test(raw)
      ? raw
      : `${raw.startsWith("localhost") || raw.startsWith("127.") ? "http" : "https"}://${raw}`;
    return [{ source: "/api/:path*", destination: `${backend.replace(/\/$/, "")}/api/:path*` }];
  },
};

export default nextConfig;
