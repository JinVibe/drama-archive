import type { DramaDetail, PersonDetail } from "@/lib/api";

export const SITE_URL = process.env.SITE_URL ?? "http://localhost:3000";

/** schema.org TVSeries for a drama page. Only canonical facts; nothing user-generated. */
export function dramaJsonLd(d: DramaDetail) {
  const actors = d.credits.filter((c) => c.creditType === "ACTOR");
  const directors = d.credits.filter((c) => c.creditType === "DIRECTOR");
  const writers = d.credits.filter((c) => c.creditType === "WRITER");
  const person = (c: { slug: string; nameKo: string }) => ({
    "@type": "Person",
    name: c.nameKo,
    url: `${SITE_URL}/persons/${c.slug}`,
  });
  return {
    "@context": "https://schema.org",
    "@type": "TVSeries",
    "@id": `${SITE_URL}/dramas/${d.slug}`,
    url: `${SITE_URL}/dramas/${d.slug}`,
    name: d.titleKo,
    alternateName: [d.titleEn, ...d.aliases].filter(Boolean),
    inLanguage: "ko",
    countryOfOrigin: { "@type": "Country", name: "KR" },
    ...(d.synopsis ? { description: d.synopsis } : {}),
    ...(d.startDate ? { startDate: d.startDate } : {}),
    ...(d.endDate ? { endDate: d.endDate } : {}),
    ...(d.episodeCount ? { numberOfEpisodes: d.episodeCount } : {}),
    ...(d.broadcaster
      ? { productionCompany: { "@type": "Organization", name: d.broadcaster.nameKo, url: d.broadcaster.officialUrl } }
      : {}),
    ...(d.genres.length ? { genre: d.genres } : {}),
    ...(actors.length ? { actor: actors.map(person) } : {}),
    ...(directors.length ? { director: directors.map(person) } : {}),
    ...(writers.length ? { author: writers.map(person) } : {}),
    ...(d.osts.length
      ? {
          hasPart: d.osts.map((o) => ({
            "@type": "MusicRecording",
            name: o.title,
            byArtist: o.artists.map((a) => ({ "@type": "MusicGroup", name: a.name })),
          })),
        }
      : {}),
  };
}

export function personJsonLd(p: PersonDetail) {
  return {
    "@context": "https://schema.org",
    "@type": "Person",
    "@id": `${SITE_URL}/persons/${p.slug}`,
    url: `${SITE_URL}/persons/${p.slug}`,
    name: p.nameKo,
    ...(p.nameEn ? { alternateName: p.nameEn } : {}),
    ...(p.birthDate ? { birthDate: p.birthDate } : {}),
    performerIn: p.filmography.map((f) => ({
      "@type": "TVSeries",
      name: f.titleKo,
      url: `${SITE_URL}/dramas/${f.slug}`,
    })),
  };
}

/** Serialize for a <script type="application/ld+json">; escapes `<` so it can never close the tag. */
export function jsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
