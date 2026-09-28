import type { Metadata } from "next";
import Link from "next/link";
import { api } from "@/lib/api";
import { Suspense } from "react";
import { Collaborators } from "@/components/Collaborators";
import { JsonLd } from "@/components/JsonLd";
import { CREDIT_LABEL, fmtDate, yearOf } from "@/lib/format";
import { personJsonLd } from "@/lib/seo";

// Rendered on demand; the static export adds generateStaticParams in its staged copy.

export async function generateMetadata({ params }: PageProps<"/persons/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const p = await api.person(slug);
  return {
    title: p.nameKo,
    description: `${p.nameKo}의 드라마 출연·제작 작품 ${p.filmography.length}편`,
    alternates: { canonical: `/persons/${p.slug}` },
  };
}

export default async function PersonPage({ params }: PageProps<"/persons/[slug]">) {
  const { slug } = await params;
  const p = await api.person(slug);

  return (
    <article className="space-y-12">
      <JsonLd data={personJsonLd(p)} />
      <header className="space-y-3 border-b border-line pb-8">
        <p className="eyebrow">Person</p>
        <h1 className="display text-[clamp(2.5rem,7vw,5.5rem)]">{p.nameKo}</h1>
        <p className="text-base text-muted">
          {[p.nameEn, p.birthDate ? `${fmtDate(p.birthDate)} 출생` : undefined].filter(Boolean).join(" · ")}
        </p>
      </header>

      <section>
        <h2 className="eyebrow mb-4">Ⅰ · 작품 {p.filmography.length}편</h2>
        <ul className="row-list">
          {p.filmography.map((f) => (
            <li key={`${f.dramaId}-${f.creditType}-${f.characterName ?? ""}`}>
              <Link
                href={`/dramas/${f.slug}`}
                className="row-link group flex items-baseline gap-4 py-3 text-sm"
              >
                <span className="w-12 shrink-0 tabular-nums text-muted">{yearOf(f.startDate) ?? ""}</span>
                <span className="text-lg font-semibold tracking-tight group-hover:text-accent">{f.titleKo}</span>
                <span className="text-muted">
                  {f.creditType === "ACTOR"
                    ? f.characterName
                      ? `${f.characterName} 역`
                      : "출연"
                    : CREDIT_LABEL[f.creditType]}
                </span>
                {f.broadcasterCode && (
                  <span className="ml-auto text-xs uppercase text-muted">{f.broadcasterCode}</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <Suspense fallback={null}>
        <Collaborators personId={p.id} />
      </Suspense>
    </article>
  );
}
