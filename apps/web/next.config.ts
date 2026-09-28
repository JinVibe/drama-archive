import type { NextConfig } from "next";

// STATIC_EXPORT=1 builds the public catalog as plain HTML for GitHub Pages
// (scripts/deploy-pages.sh): every drama/person/year page pre-rendered from the
// local stack, search in the browser over public/search-index.json, watch state
// in localStorage. Server-only routes (/api proxy, /admin, /share) are removed
// by the deploy script before building. Default: the self-contained server image.
const isStatic = process.env.STATIC_EXPORT === "1";
const basePath = process.env.BASE_PATH ?? "";

const nextConfig: NextConfig = isStatic
  ? {
      output: "export",
      basePath,
      trailingSlash: true,
      images: { unoptimized: true },
      env: { NEXT_PUBLIC_STATIC: "1", NEXT_PUBLIC_BASE_PATH: basePath },
    }
  : {
      // Self-contained server for the Docker image.
      output: "standalone",
      // /api/* is proxied to the Domain API at runtime by src/app/api/[...path]/route.ts
      // (not via `rewrites`, which would freeze DOMAIN_API_URL into the build).
    };

export default nextConfig;
