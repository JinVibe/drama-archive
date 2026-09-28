import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { api } from "@/lib/api";
import { YearList } from "@/components/YearList";

function parseYear(raw: string): number {
  const year = Number(raw);
  if (!Number.isInteger(year) || year < 1950 || year > 2100) notFound();
  return year;
}

// Rendered on demand; the static export adds generateStaticParams in its staged copy.

export async function generateMetadata({ params }: PageProps<"/years/[year]">): Promise<Metadata> {
  const { year } = await params;
  return {
    title: `${year}년 드라마`,
    description: `${year}년에 방영한 한국 드라마를 방송사별로 모아 봅니다.`,
  };
}

export default async function YearPage({ params }: PageProps<"/years/[year]">) {
  const { year: rawYear } = await params;
  const year = parseYear(rawYear);

  // The channel filter (?broadcaster=) is applied in the browser (YearList), so the
  // page itself is the same for every filter and can be pre-rendered.
  const [page, broadcasters, years] = await Promise.all([
    api.year(year, undefined, 0, 200),
    api.broadcasters(),
    api.years(),
  ]);
  const idx = years.findIndex((y) => y.year === year);
  const newer = idx > 0 ? years[idx - 1] : undefined;
  const older = idx >= 0 && idx < years.length - 1 ? years[idx + 1] : undefined;

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="eyebrow">Ⅰ · 연도별</p>
          <h1 className="display mt-3 text-[clamp(3.5rem,12vw,8rem)] tabular-nums">{year}</h1>
          <p className="mt-2 text-sm text-muted">{page.total}편</p>
        </div>
        <nav className="flex gap-3 text-sm">
          {older ? (
            <Link href={`/years/${older.year}`} className="btn">
              ← {older.year}
            </Link>
          ) : (
            <span className="btn opacity-30">←</span>
          )}
          {newer ? (
            <Link href={`/years/${newer.year}`} className="btn">
              {newer.year} →
            </Link>
          ) : (
            <span className="btn opacity-30">→</span>
          )}
        </nav>
      </header>

      <Suspense fallback={null}>
        <YearList year={year} items={page.items} broadcasters={broadcasters} />
      </Suspense>
    </div>
  );
}
