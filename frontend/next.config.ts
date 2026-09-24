import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the dev-mode "N" badge so it doesn't cover the sidebar during demos.
  devIndicators: false,
};

export default nextConfig;
