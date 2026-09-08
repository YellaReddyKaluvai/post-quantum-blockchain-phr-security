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
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
