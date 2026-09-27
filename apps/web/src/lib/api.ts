/**
 * Server-side client for the Domain API (public catalog reads).
 * Runs only in Server Components / route handlers; the browser goes through the
 * /api rewrite instead (see next.config.ts and lib/client.ts).
 */
import { notFound, redirect } from "next/navigation";

const BASE = process.env.DOMAIN_API_URL ?? "http://localhost:8081";
/** Public catalog pages revalidate on this cadence (seconds). */
export const CATALOG_REVALIDATE = 60;

export type Broadcaster = { code: string; nameKo: string; nameEn?: string; officialUrl?: string };
export type YearCount = { year: number; count: number };
export type DramaSummary = {
  id: number;
  slug: string;
  titleKo: string;
  titleEn?: string;
  broadcaster?: Broadcaster;
  startDate?: string;
  endDate?: string;
  episodeCount?: number;
  genres: string[];
};
export type Page<T> = { items: T[]; page: number; size: number; total: number };
export type Credit = {
  personId: number;
  slug: string;
  nameKo: string;
  nameEn?: string;
  creditType: "ACTOR" | "DIRECTOR" | "WRITER" | "PRODUCER";
  characterName?: string;
  billingOrder?: number;
  mainCast: boolean;
};
export type Ost = {
  songId: number;
  title: string;
  releaseDate?: string;
  partNo?: number;
  trackNo?: number;
  artists: { id: number; name: string; role: string }[];
};
export type WatchLink = {
  providerCode: string;
  url: string;
  linkType: string;
  regionCode: string;
  availabilityStatus: string;
  lastVerifiedAt?: string;
};
export type DramaDetail = DramaSummary & {
  aliases: string[];
  runtimeMinutes?: number;
  synopsis?: string;
  officialPageUrl?: string;
  credits: Credit[];
  osts: Ost[];
  links: WatchLink[];
  canonicalVersion: number;
};
export type FilmographyEntry = {
  dramaId: number;
  slug: string;
  titleKo: string;
  broadcasterCode?: string;
  startDate?: string;
  creditType: Credit["creditType"];
  characterName?: string;
  mainCast: boolean;
};
export type PersonDetail = {
  id: number;
  slug: string;
  nameKo: string;
  nameEn?: string;
  birthDate?: string;
  filmography: FilmographyEntry[];
};

/**
 * GET a catalog resource. 404 -> notFound(); 301 (merged entity) -> redirect the
 * browser to the surviving slug so the canonical URL is what gets indexed.
 */
async function get<T>(path: string, pageForSlug?: (slug: string) => string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    next: { revalidate: CATALOG_REVALIDATE },
    redirect: "manual",
  });
  if (res.status === 404) notFound();
  if (res.status === 301 && pageForSlug) {
    const location = res.headers.get("location") ?? "";
    const slug = location.substring(location.lastIndexOf("/") + 1);
    redirect(pageForSlug(slug));
  }
  if (!res.ok) throw new Error(`Domain API ${res.status} for ${path}`);
  return (await res.json()) as T;
}

export const api = {
  broadcasters: () => get<Broadcaster[]>("/api/v1/broadcasters"),
  years: () => get<YearCount[]>("/api/v1/years"),
  year: (year: number, broadcaster?: string, page = 0, size = 100) => {
    const q = new URLSearchParams({ page: String(page), size: String(size) });
    if (broadcaster) q.set("broadcaster", broadcaster);
    return get<Page<DramaSummary>>(`/api/v1/years/${year}?${q}`);
  },
  drama: (slug: string) =>
    get<DramaDetail>(`/api/v1/dramas/${encodeURIComponent(slug)}`, (s) => `/dramas/${s}`),
  person: (slug: string) =>
    get<PersonDetail>(`/api/v1/persons/${encodeURIComponent(slug)}`, (s) => `/persons/${s}`),
};
