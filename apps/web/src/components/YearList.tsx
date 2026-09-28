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

  return (
    <>
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
