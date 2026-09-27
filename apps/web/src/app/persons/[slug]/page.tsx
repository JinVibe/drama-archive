import type { Metadata } from "next";
import Link from "next/link";
import { api } from "@/lib/api";
import { CREDIT_LABEL, fmtDate, yearOf } from "@/lib/format";

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
    <article className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{p.nameKo}</h1>
        <p className="text-sm text-muted">
          {[p.nameEn, p.birthDate ? `${fmtDate(p.birthDate)} 출생` : undefined].filter(Boolean).join(" · ")}
        </p>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">
          작품 {p.filmography.length}편
        </h2>
        <ul className="divide-y divide-line rounded-md border border-line bg-card">
          {p.filmography.map((f) => (
            <li key={`${f.dramaId}-${f.creditType}-${f.characterName ?? ""}`}>
              <Link
                href={`/dramas/${f.slug}`}
                className="flex items-baseline gap-3 px-3 py-2 text-sm hover:text-accent"
              >
                <span className="w-12 shrink-0 text-muted">{yearOf(f.startDate) ?? ""}</span>
                <span className="font-medium">{f.titleKo}</span>
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
    </article>
  );
}
