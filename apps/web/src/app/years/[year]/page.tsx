import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { DramaCard } from "@/components/DramaCard";

function parseYear(raw: string): number {
  const year = Number(raw);
  if (!Number.isInteger(year) || year < 1950 || year > 2100) notFound();
  return year;
}

export async function generateMetadata({ params }: PageProps<"/years/[year]">): Promise<Metadata> {
  const { year } = await params;
  return {
    title: `${year}년 드라마`,
    description: `${year}년에 방영한 한국 드라마를 방송사별로 모아 봅니다.`,
  };
}

export default async function YearPage({ params, searchParams }: PageProps<"/years/[year]">) {
  const { year: rawYear } = await params;
  const { broadcaster: rawBc } = await searchParams;
  const year = parseYear(rawYear);
  const broadcaster = typeof rawBc === "string" ? rawBc : undefined;

  const [page, broadcasters, years] = await Promise.all([
    api.year(year, broadcaster),
    api.broadcasters(),
    api.years(),
  ]);
  const idx = years.findIndex((y) => y.year === year);
  const newer = idx > 0 ? years[idx - 1] : undefined;
  const older = idx >= 0 && idx < years.length - 1 ? years[idx + 1] : undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">{year}년</h1>
        <nav className="flex gap-3 text-sm text-muted">
          {older && <Link href={`/years/${older.year}`}>← {older.year}</Link>}
          {newer && <Link href={`/years/${newer.year}`}>{newer.year} →</Link>}
        </nav>
      </div>

      <ul className="flex flex-wrap gap-2 text-sm">
        <li>
          <Link
            href={`/years/${year}`}
            className={`rounded-full border px-3 py-1 ${!broadcaster ? "border-accent text-accent" : "border-line"}`}
          >
            전체
          </Link>
        </li>
        {broadcasters.map((b) => (
          <li key={b.code}>
            <Link
              href={`/years/${year}?broadcaster=${b.code}`}
              className={`rounded-full border px-3 py-1 ${broadcaster === b.code ? "border-accent text-accent" : "border-line"}`}
            >
              {b.nameKo}
            </Link>
          </li>
        ))}
      </ul>

      {page.total === 0 ? (
        <p className="text-muted">이 조건에 맞는 작품이 아직 없습니다.</p>
      ) : (
        <>
          <p className="text-sm text-muted">{page.total}편</p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {page.items.map((d) => (
              <li key={d.id}>
                <DramaCard drama={d} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
