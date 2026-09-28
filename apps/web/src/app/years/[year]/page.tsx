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
    api.year(year, broadcaster, 0, 200),
    api.broadcasters(),
    api.years(),
  ]);
  const idx = years.findIndex((y) => y.year === year);
  const newer = idx > 0 ? years[idx - 1] : undefined;
  const older = idx >= 0 && idx < years.length - 1 ? years[idx + 1] : undefined;
  const filterName = broadcasters.find((b) => b.code === broadcaster)?.nameKo;

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="eyebrow">Ⅰ · 연도별{filterName ? ` · ${filterName}` : ""}</p>
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

      <ul className="flex flex-wrap gap-x-5 gap-y-2 border-b border-line pb-3 text-sm">
        <li>
          <Link
            href={`/years/${year}`}
            className={!broadcaster ? "text-accent" : "text-muted hover:text-foreground"}
          >
            전체
          </Link>
        </li>
        {broadcasters.map((b) => (
          <li key={b.code}>
            <Link
              href={`/years/${year}?broadcaster=${b.code}`}
              className={broadcaster === b.code ? "text-accent" : "text-muted hover:text-foreground"}
            >
              {b.nameKo}
            </Link>
          </li>
        ))}
      </ul>

      {page.total === 0 ? (
        <p className="text-muted">이 조건에 맞는 작품이 아직 없습니다.</p>
      ) : (
        <ul className="row-list">
          {page.items.map((d) => (
            <li key={d.id}>
              <DramaCard drama={d} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
