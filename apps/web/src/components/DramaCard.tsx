import Link from "next/link";
import type { DramaSummary } from "@/lib/api";
import { fmtDate, genreLabel } from "@/lib/format";

/** Index row: title first, everything else recedes. */
export function DramaCard({ drama }: { drama: DramaSummary }) {
  return (
    <Link href={`/dramas/${drama.slug}`} className="row-link group grid gap-1 py-4 md:grid-cols-[7rem_1fr_auto] md:items-baseline md:gap-6">
      <span className="text-xs tabular-nums text-muted">{fmtDate(drama.startDate) || "—"}</span>
      <span>
        <span className="text-lg font-semibold tracking-tight group-hover:text-accent md:text-xl">{drama.titleKo}</span>
        {drama.titleEn && <span className="ml-3 text-sm text-muted">{drama.titleEn}</span>}
      </span>
      <span className="flex flex-wrap items-baseline gap-x-3 text-xs text-muted md:justify-end">
        {drama.broadcaster && <span className="text-foreground">{drama.broadcaster.nameKo}</span>}
        {drama.episodeCount ? <span>{drama.episodeCount}부작</span> : null}
        {drama.genres.length > 0 && <span>{drama.genres.map(genreLabel).join(" · ")}</span>}
      </span>
    </Link>
  );
}
