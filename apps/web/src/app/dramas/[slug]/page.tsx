import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { api } from "@/lib/api";
import { JsonLd } from "@/components/JsonLd";
import { MemoryNote } from "@/components/MemoryNote";
import { RelatedDramas } from "@/components/RelatedDramas";
import { WatchButtons } from "@/components/WatchButtons";
import { dramaJsonLd } from "@/lib/seo";
import { CREDIT_LABEL, LINK_LABEL, fmtDate, fmtRange, genreLabel, yearOf } from "@/lib/format";

export async function generateMetadata({ params }: PageProps<"/dramas/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const d = await api.drama(slug);
  const year = yearOf(d.startDate);
  const title = `${d.titleKo}${year ? ` (${year})` : ""}`;
  const description =
    d.synopsis ??
    `${d.broadcaster?.nameKo ?? ""} ${year ?? ""} 드라마 ${d.titleKo} — 출연진, OST, 공식 다시보기`;
  return {
    title,
    description,
    alternates: { canonical: `/dramas/${d.slug}` },
    openGraph: { title, description, type: "video.tv_show", url: `/dramas/${d.slug}` },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function DramaPage({ params }: PageProps<"/dramas/[slug]">) {
  const { slug } = await params;
  const d = await api.drama(slug);
  const year = yearOf(d.startDate);
  const cast = d.credits.filter((c) => c.creditType === "ACTOR");
  const crew = d.credits.filter((c) => c.creditType !== "ACTOR");

  return (
    <article className="space-y-8">
      <JsonLd data={dramaJsonLd(d)} />
      <header className="space-y-3">
        <p className="text-sm text-muted">
          {year && (
            <Link href={`/years/${year}`} className="hover:text-accent">
              {year}년
            </Link>
          )}
          {d.broadcaster && (
            <>
              {" · "}
              <Link href={`/years/${year}?broadcaster=${d.broadcaster.code}`} className="hover:text-accent">
                {d.broadcaster.nameKo}
              </Link>
            </>
          )}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{d.titleKo}</h1>
        {(d.titleEn || d.aliases.length > 0) && (
          <p className="text-sm text-muted">{[d.titleEn, ...d.aliases].filter(Boolean).join(" · ")}</p>
        )}
        <p className="text-sm text-muted">
          {fmtRange(d.startDate, d.endDate)}
          {d.episodeCount ? ` · ${d.episodeCount}부작` : ""}
          {d.runtimeMinutes ? ` · ${d.runtimeMinutes}분` : ""}
        </p>
        {d.genres.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {d.genres.map((g) => (
              <li key={g} className="rounded bg-accent-soft px-2 py-0.5 text-xs text-accent">
                {genreLabel(g)}
              </li>
            ))}
          </ul>
        )}
        <WatchButtons dramaId={d.id} />
        <MemoryNote dramaId={d.id} />
      </header>

      {d.synopsis && <p className="max-w-3xl leading-relaxed">{d.synopsis}</p>}

      {d.links.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">다시보기</h2>
          <ul className="flex flex-wrap gap-2">
            {d.links.map((l) => (
              <li key={l.url}>
                <a
                  href={l.url}
                  rel="noopener noreferrer nofollow"
                  target="_blank"
                  className="rounded-md border border-line bg-card px-3 py-1.5 text-sm hover:border-accent"
                >
                  {LINK_LABEL[l.linkType] ?? l.linkType} · {l.providerCode.toUpperCase()}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {cast.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">출연</h2>
          <ul className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
            {cast.map((c) => (
              <li key={`${c.personId}-${c.characterName ?? ""}`}>
                <Link
                  href={`/persons/${c.slug}`}
                  className="flex items-baseline justify-between rounded-md border border-line bg-card px-3 py-2 hover:border-accent"
                >
                  <span className="font-medium">{c.nameKo}</span>
                  {c.characterName && <span className="text-sm text-muted">{c.characterName} 역</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {crew.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">제작진</h2>
          <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {crew.map((c) => (
              <li key={`${c.personId}-${c.creditType}`}>
                <span className="text-muted">{CREDIT_LABEL[c.creditType]} </span>
                <Link href={`/persons/${c.slug}`} className="hover:text-accent">
                  {c.nameKo}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.osts.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">OST</h2>
          <ol className="divide-y divide-line rounded-md border border-line bg-card">
            {d.osts.map((o) => (
              <li key={o.songId} className="flex items-baseline gap-3 px-3 py-2 text-sm">
                <span className="w-12 shrink-0 text-muted">{o.partNo ? `Part ${o.partNo}` : ""}</span>
                <span className="font-medium">{o.title}</span>
                <span className="text-muted">{o.artists.map((a) => a.name).join(", ")}</span>
                {o.releaseDate && <span className="ml-auto text-xs text-muted">{fmtDate(o.releaseDate)}</span>}
              </li>
            ))}
          </ol>
        </section>
      )}

      <Suspense fallback={null}>
        <RelatedDramas dramaId={d.id} />
      </Suspense>
    </article>
  );
}
