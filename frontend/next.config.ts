import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the dev-mode "N" badge so it doesn't cover the sidebar during demos.
  devIndicators: false,
  // Self-contained server bundle for the Docker image (frontend/Dockerfile).
  output: "standalone",
  // The dashboard is its own project; don't treat the repository root's lockfile as its workspace.
  outputFileTracingRoot: process.cwd(),
  turbopack: { root: process.cwd() },
};

export default nextConfig;
