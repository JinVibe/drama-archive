import type { Metadata } from "next";
import Link from "next/link";
import { CATALOG_REVALIDATE } from "@/lib/api";
import { genreLabel } from "@/lib/format";

export const metadata: Metadata = { title: "검색", robots: { index: false } };
export const dynamic = "force-dynamic";

type Hit = {
  dramaId: number;
  title: string;
  metadata: {
    slug: string;
    year?: number;
    broadcaster_name?: string;
    genres?: string[];
    cast?: string[];
    title_en?: string;
  };
  inFts: boolean;
  inTrigram: boolean;
};
type Result = { query: string; strategy: string; total: number; hits: Hit[]; latencyMs: number };

async function search(q: string): Promise<Result> {
  const base = process.env.DOMAIN_API_URL ?? "http://localhost:8081";
  const res = await fetch(`${base}/api/v1/search?${new URLSearchParams({ q, size: "30" })}`, {
    next: { revalidate: CATALOG_REVALIDATE },
  });
  if (!res.ok) throw new Error(`search ${res.status}`);
  return res.json();
}

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const { q: raw } = await searchParams;
  const q = (typeof raw === "string" ? raw : "").trim();
  const result = q ? await search(q) : null;

  return (
    <div className="space-y-6">
      <form action="/search" className="flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="제목, 배우, 배역, OST, 장르… 예) 공유 판타지"
          className="flex-1 rounded-md border border-line bg-card px-3 py-2 focus:border-accent focus:outline-none"
          autoFocus
        />
        <button type="submit" className="rounded-md bg-accent px-4 py-2 text-white">
          검색
        </button>
      </form>

      {result && (
        <>
          <p className="text-sm text-muted">
            “{result.query}” {result.total}건 · {result.latencyMs}ms
            {result.strategy !== "NONE" && <span className="ml-2 text-xs">[{result.strategy}]</span>}
          </p>
          {result.total === 0 ? (
            <p className="text-muted">
              찾지 못했어요. 제목이 기억나지 않으면 배우 이름이나 OST 제목으로 검색해 보세요.
            </p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {result.hits.map((h) => (
                <li key={h.dramaId}>
                  <Link
                    href={`/dramas/${h.metadata.slug}`}
                    className="block rounded-lg border border-line bg-card p-4 transition hover:border-accent"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="font-semibold">{h.title}</h3>
                      {h.metadata.broadcaster_name && (
                        <span className="shrink-0 rounded bg-accent-soft px-2 py-0.5 text-xs text-accent">
                          {h.metadata.broadcaster_name}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      {[h.metadata.year ? `${h.metadata.year}년` : null, h.metadata.genres?.map(genreLabel).join(" · ")]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    {h.metadata.cast && h.metadata.cast.length > 0 && (
                      <p className="mt-1 text-xs text-muted">{h.metadata.cast.slice(0, 5).join(", ")}</p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
