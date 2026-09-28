import type { MetadataRoute } from "next";
import { api } from "@/lib/api";

const SITE = process.env.SITE_URL ?? "http://localhost:3000";

// Server mode: rendered per request (uncached fetches, so the build never needs the
// Domain API). Static export: written once at build time.

/** Public catalog only; user pages are never listed. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const years = await api.years();
  const pages = await Promise.all(years.map((y) => api.year(y.year, undefined, 0, 200)));
  const dramas = pages.flatMap((p) => p.items);
  return [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    ...years.map((y) => ({ url: `${SITE}/years/${y.year}`, changeFrequency: "weekly" as const, priority: 0.8 })),
    ...dramas.map((d) => ({ url: `${SITE}/dramas/${d.slug}`, changeFrequency: "weekly" as const, priority: 0.7 })),
  ];
}
