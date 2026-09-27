import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server for the Docker image.
  output: "standalone",
  // /api/* is proxied to the Domain API at runtime by src/app/api/[...path]/route.ts
  // (not via `rewrites`, which would freeze DOMAIN_API_URL into the build).
};

export default nextConfig;
