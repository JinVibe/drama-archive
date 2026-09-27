import type { Metadata } from "next";
import Link from "next/link";
import { CATALOG_REVALIDATE } from "@/lib/api";
import { genreLabel } from "@/lib/format";

export const metadata: Metadata = { title: "검색", robots: { index: false } };
export const dynamic = "force-dynamic";

type Meta = {
  slug: string;
  year?: number;
  broadcaster_name?: string;
  genres?: string[];
  cast?: string[];
  title_en?: string;
};
type Hit = { dramaId: number; title: string; metadata: Meta; evidence: string[] };
type Plan = { text: string; year_from?: number | null; year_to?: number | null; broadcaster?: string | null };
type Result = {
  query: string;
  engine: "ai" | "lexical";
  strategy: string;
  total: number;
  hits: Hit[];
  latencyMs: number;
  plan?: Plan;
  relaxed?: boolean;
};

const AI_API = process.env.AI_API_URL ?? "http://localhost:8090";
const DOMAIN_API = process.env.DOMAIN_API_URL ?? "http://localhost:8081";

/**
 * Hybrid search from ai-api (query analysis + lexical + vector, RRF). If ai-api is
 * down, degrade to the Domain API's lexical search instead of failing the page
 * (docs/ARCHITECTURE.md §11 failure modes).
 */
async function search(q: string): Promise<Result> {
  const opts = { next: { revalidate: CATALOG_REVALIDATE } };
  try {
    const started = Date.now();
    const res = await fetch(`${AI_API}/v1/search?${new URLSearchParams({ q, size: "30" })}`, {
      ...opts,
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      const b = await res.json();
      return {
        query: b.query,
        engine: "ai",
        strategy: b.strategy,
        total: b.total,
        latencyMs: Date.now() - started,
        plan: b.plan,
        relaxed: b.relaxed,
        hits: b.hits.map((h: { drama_id: number; title: string; metadata: Meta; ranks: Record<string, number> }) => ({
          dramaId: h.drama_id,
          title: h.title,
          metadata: h.metadata,
          evidence: Object.entries(h.ranks).map(([k, r]) => `${k}#${r}`),
        })),
      };
    }
  } catch {
    // fall through to lexical
  }
  const res = await fetch(`${DOMAIN_API}/api/v1/search?${new URLSearchParams({ q, size: "30" })}`, opts);
  if (!res.ok) throw new Error(`search ${res.status}`);
  const b = await res.json();
  return {
    query: b.query,
    engine: "lexical",
    strategy: b.strategy,
    total: b.total,
    latencyMs: b.latencyMs,
    hits: b.hits.map((h: { dramaId: number; title: string; metadata: Meta; inFts: boolean; inTrigram: boolean }) => ({
      dramaId: h.dramaId,
      title: h.title,
      metadata: h.metadata,
      evidence: [h.inFts ? "fts" : null, h.inTrigram ? "trigram" : null].filter(Boolean) as string[],
    })),
  };
}

function planLabel(p?: Plan): string | null {
  if (!p) return null;
  const parts: string[] = [];
  if (p.year_from) parts.push(p.year_from === p.year_to ? `${p.year_from}년` : `${p.year_from}–${p.year_to}년`);
  if (p.broadcaster) parts.push(p.broadcaster.toUpperCase());
  if (p.text) parts.push(`“${p.text}”`);
  return parts.length ? parts.join(" · ") : null;
}

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const { q: raw } = await searchParams;
  const q = (typeof raw === "string" ? raw : "").trim();
  const result = q ? await search(q) : null;
  const plan = planLabel(result?.plan);

  return (
    <div className="space-y-6">
      <form action="/search" className="flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="기억나는 대로 적어 보세요. 예) 2016년쯤 겨울에 공유 나온 판타지"
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
            {result.total}건 · {result.latencyMs}ms
            {plan && <span className="ml-2">이해한 조건: {plan}</span>}
            {result.relaxed && <span className="ml-2">(조건에 맞는 작품이 없어 조건 없이 검색했어요)</span>}
            <span className="ml-2 text-xs">
              [{result.engine === "ai" ? "AI 검색" : "기본 검색"} · {result.strategy}]
            </span>
          </p>
          {result.total === 0 ? (
            <p className="text-muted">
              찾지 못했어요. 배우 이름, 배역, OST, 줄거리의 한 장면처럼 기억나는 것을 더 적어 보세요.
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
                    <p className="mt-2 text-[11px] text-muted" title="어떤 검색기가 찾았는지">
                      {h.evidence.join(" · ")}
                    </p>
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
