#!/usr/bin/env node
/**
 * Browser search index for the static export (GitHub Pages): one JSON row per
 * published drama with the words a person would type — title, aliases, cast,
 * characters, a slice of the plot. Read from the local Domain API at build time.
 *
 *   DOMAIN_API_URL=http://localhost:8081 node scripts/build-search-index.mjs
 * writes public/search-index.json (~1 MB for 2,000 dramas).
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE = process.env.DOMAIN_API_URL ?? "http://localhost:8081";
const OUT = path.join(process.cwd(), "public", "search-index.json");

async function get(p) {
  const res = await fetch(`${BASE}${p}`);
  if (!res.ok) throw new Error(`${p} -> ${res.status}`);
  return res.json();
}

const years = await get("/api/v1/years");
const pages = await Promise.all(years.map((y) => get(`/api/v1/years/${y.year}?size=200`)));
const summaries = pages.flatMap((p) => p.items);

const rows = [];
let done = 0;
for (const s of summaries) {
  const d = await get(`/api/v1/dramas/${encodeURIComponent(s.slug)}`);
  const cast = d.credits.filter((c) => c.creditType === "ACTOR");
  rows.push({
    id: d.id,
    slug: d.slug,
    title: d.titleKo,
    titleEn: d.titleEn ?? undefined,
    aliases: d.aliases.join(" "),
    year: d.startDate ? Number(d.startDate.slice(0, 4)) : undefined,
    broadcaster: d.broadcaster?.code,
    broadcasterName: d.broadcaster?.nameKo,
    genres: d.genres,
    cast: cast.map((c) => c.nameKo).join(", "),
    characters: cast.map((c) => c.characterName).filter(Boolean).join(" "),
    synopsis: (d.synopsis ?? "").slice(0, 400),
  });
  if (++done % 200 === 0) console.log(`${done}/${summaries.length}`);
}

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify(rows), "utf8");
console.log(`search index: ${rows.length} dramas -> ${OUT}`);
