"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { Broadcaster, DramaSummary } from "@/lib/api";
import { DramaCard } from "@/components/DramaCard";

/** Year archive list with the channel filter read from ?broadcaster= in the browser,
 *  so the page is one static document per year. */
export function YearList({
  year,
  items,
  broadcasters,
}: {
  year: number;
  items: DramaSummary[];
  broadcasters: Broadcaster[];
}) {
  const params = useSearchParams();
  const broadcaster = params.get("broadcaster")?.toLowerCase() || undefined;
  const shown = broadcaster ? items.filter((d) => d.broadcaster?.code === broadcaster) : items;
  const filterName = broadcasters.find((b) => b.code === broadcaster)?.nameKo;
  // "그해의 인기작": the five most-read Korean Wikipedia articles of the year (a proxy,
  // labelled as such). Only when enough dramas carry the number.
  const featured = shown
    .filter((d) => (d.popularity ?? 0) > 0)
    .sort((a, b) => (b.popularity ?? 0) - (a.popularity ?? 0))
    .slice(0, 5);
  const showFeatured = featured.length >= 3 && shown.length > 6;

  return (
    <>
      {showFeatured && (
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="eyebrow">그해의 인기작{filterName ? ` · ${filterName}` : ""}</h2>
            <span className="text-[11px] text-muted" title="한국어 위키백과 문서의 최근 1년 조회수 기준 — 시청률이 아닙니다">
              위키백과 조회수 기준
            </span>
          </div>
          <ol className="grid gap-2 sm:grid-cols-5">
            {featured.map((d, i) => (
              <li key={d.id}>
                <Link
                  href={`/dramas/${d.slug}`}
                  className="group flex h-full flex-col justify-between rounded-lg border border-line bg-card px-4 py-3 transition hover:border-line-strong hover:bg-card-2"
                >
                  <span className="display text-2xl text-accent">{i + 1}</span>
                  <span className="mt-2 text-base font-semibold tracking-tight group-hover:text-accent">{d.titleKo}</span>
                  <span className="mt-1 text-xs text-muted">{d.broadcaster?.nameKo ?? ""}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}
      <ul className="flex flex-wrap gap-x-5 gap-y-2 border-b border-line pb-3 text-sm">
        <li>
          <Link href={`/years/${year}`} className={!broadcaster ? "text-accent" : "text-muted hover:text-foreground"}>
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
        {filterName && <li className="ml-auto text-muted">{filterName} {shown.length}편</li>}
      </ul>

      {shown.length === 0 ? (
        <p className="text-muted">이 조건에 맞는 작품이 아직 없습니다.</p>
      ) : (
        <ul className="row-list">
          {shown.map((d) => (
            <li key={d.id}>
              <DramaCard drama={d} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
