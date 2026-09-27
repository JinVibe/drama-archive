import Link from "next/link";
import type { DramaSummary } from "@/lib/api";
import { fmtRange, genreLabel } from "@/lib/format";

export function DramaCard({ drama }: { drama: DramaSummary }) {
  return (
    <Link
      href={`/dramas/${drama.slug}`}
      className="block rounded-lg border border-line bg-card p-4 transition hover:border-accent"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">{drama.titleKo}</h3>
        {drama.broadcaster && (
          <span className="shrink-0 rounded bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
            {drama.broadcaster.nameKo}
          </span>
        )}
      </div>
      {drama.titleEn && <p className="text-xs text-muted">{drama.titleEn}</p>}
      <p className="mt-2 text-sm text-muted">
        {fmtRange(drama.startDate, drama.endDate)}
        {drama.episodeCount ? ` · ${drama.episodeCount}부작` : ""}
      </p>
      {drama.genres.length > 0 && (
        <p className="mt-1 text-xs text-muted">{drama.genres.map(genreLabel).join(" · ")}</p>
      )}
    </Link>
  );
}
