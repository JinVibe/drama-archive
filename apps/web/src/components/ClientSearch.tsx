"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import MiniSearch from "minisearch";
import { genreLabel } from "@/lib/format";

/** One row of public/search-index.json (scripts/build-search-index.mjs). */
type Doc = {
  id: number;
  slug: string;
  title: string;
  titleEn?: string;
  aliases: string;
  year?: number;
  broadcaster?: string;
  broadcasterName?: string;
  genres: string[];
  cast: string;
  characters: string;
  synopsis: string;
};

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const YEAR = /(?:^|\s)((?:19|20)\d{2})\s*년?(쯤|경)?/;
const CHANNEL: Record<string, string> = {
  kbs: "kbs", mbc: "mbc", sbs: "sbs", tvn: "tvn", jtbc: "jtbc",
  케이비에스: "kbs", 엠비씨: "mbc", 에스비에스: "sbs", 티비엔: "tvn", 제이티비씨: "jtbc",
};

/** Korean has no word boundaries inside compounds: index whitespace tokens plus
 *  character bigrams so "공유판타지" and "판타지 로맨스" both find 도깨비. */
function tokenize(text: string): string[] {
  const out: string[] = [];
  for (const word of text.toLowerCase().split(/[^0-9a-z가-힣]+/)) {
    if (!word) continue;
    out.push(word);
    if (/[가-힣]/.test(word) && word.length > 2) {
      for (let i = 0; i < word.length - 1; i++) out.push(word.slice(i, i + 2));
    }
  }
  return out;
}

function analyze(raw: string) {
  let text = raw.trim();
  let yearFrom: number | undefined;
  let yearTo: number | undefined;
  const y = YEAR.exec(text);
  if (y) {
    const year = Number(y[1]);
    yearFrom = y[2] ? year - 1 : year;
    yearTo = y[2] ? year + 1 : year;
    text = text.replace(y[0], " ");
  }
  let broadcaster: string | undefined;
  for (const [alias, code] of Object.entries(CHANNEL)) {
    const re = new RegExp(`(^|\\s)${alias}(\\s|$)`, "i");
    if (re.test(text)) {
      broadcaster = code;
      text = text.replace(re, " ");
      break;
    }
  }
  text = text.replace(/\s+/g, " ").trim();
  return { text, yearFrom, yearTo, broadcaster };
}

export function ClientSearch() {
  const params = useSearchParams();
  const router = useRouter();
  const q = (params.get("q") ?? "").trim();
  const [draft, setDraft] = useState(q);
  const [prevQ, setPrevQ] = useState(q);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [error, setError] = useState(false);

  // Back/forward navigation changes ?q= without remounting: adjust the draft during render.
  if (q !== prevQ) {
    setPrevQ(q);
    setDraft(q);
  }
  useEffect(() => {
    fetch(`${BASE}/search-index.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: Doc[]) => setDocs(d))
      .catch(() => setError(true));
  }, []);

  const index = useMemo(() => {
    if (!docs) return null;
    const ms = new MiniSearch<Doc>({
      fields: ["title", "titleEn", "aliases", "cast", "characters", "synopsis"],
      storeFields: ["slug", "title", "year", "broadcasterName", "genres", "cast", "broadcaster"],
      tokenize,
      searchOptions: {
        boost: { title: 4, aliases: 3, cast: 2, characters: 2 },
        prefix: true,
        combineWith: "OR",
      },
    });
    ms.addAll(docs);
    return ms;
  }, [docs]);

  const plan = useMemo(() => analyze(q), [q]);
  const hits = useMemo(() => {
    if (!index || !docs) return [];
    const byId = new Map(docs.map((d) => [d.id, d]));
    const inScope = (d: Doc) =>
      (plan.yearFrom === undefined || (d.year !== undefined && d.year >= plan.yearFrom && d.year <= plan.yearTo!)) &&
      (!plan.broadcaster || d.broadcaster === plan.broadcaster);
    let results = plan.text
      ? index.search(plan.text).map((r) => byId.get(r.id as number)!).filter(Boolean)
      : plan.yearFrom !== undefined || plan.broadcaster
        ? docs.slice()
        : [];
    let relaxed = false;
    const scoped = results.filter(inScope);
    if (scoped.length > 0) results = scoped;
    else if (plan.text && (plan.yearFrom !== undefined || plan.broadcaster)) relaxed = true;
    return { list: results.slice(0, 30), relaxed, total: results.length } as const;
  }, [index, docs, plan]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const next = draft.trim();
    router.push(next ? `/search/?q=${encodeURIComponent(next)}` : "/search/");
  }

  const planParts = [
    plan.yearFrom !== undefined ? (plan.yearFrom === plan.yearTo ? `${plan.yearFrom}년` : `${plan.yearFrom}–${plan.yearTo}년`) : null,
    plan.broadcaster?.toUpperCase(),
    plan.text ? `“${plan.text}”` : null,
  ].filter(Boolean);

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="flex gap-3">
        <input
          type="search"
          name="q"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="기억나는 대로 적어 보세요. 예) 2016년쯤 겨울에 공유 나온 판타지"
          className="display flex-1 border-b border-line-strong bg-transparent px-1 py-3 text-2xl font-semibold tracking-tight placeholder:font-normal placeholder:text-muted focus:border-accent focus:outline-none md:text-4xl"
          autoFocus
        />
        <button type="submit" className="btn btn-primary self-end">
          검색
        </button>
      </form>

      {error && <p className="text-muted">검색 인덱스를 불러오지 못했어요.</p>}
      {q && !error && (
        <>
          <p className="text-sm text-muted">
            {docs ? `${"total" in hits ? hits.total : 0}건` : "인덱스 불러오는 중…"}
            {planParts.length > 0 && <span className="ml-2">이해한 조건: {planParts.join(" · ")}</span>}
            {"relaxed" in hits && hits.relaxed && <span className="ml-2">(조건에 맞는 작품이 없어 조건 없이 검색했어요)</span>}
            <span className="ml-2 text-xs">[브라우저 검색 · 제목·별칭·출연진·배역·줄거리]</span>
          </p>
          {docs && "list" in hits && hits.list.length === 0 && (
            <p className="text-muted">찾지 못했어요. 배우 이름, 배역, 줄거리의 한 장면처럼 기억나는 것을 더 적어 보세요.</p>
          )}
          {"list" in hits && hits.list.length > 0 && (
            <ul className="row-list">
              {hits.list.map((h) => (
                <li key={h.id}>
                  <Link href={`/dramas/${h.slug}`} className="row-link group py-4">
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="text-xl font-semibold tracking-tight group-hover:text-accent">{h.title}</h3>
                      {h.broadcasterName && <span className="shrink-0 text-xs text-muted">{h.broadcasterName}</span>}
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      {[h.year ? `${h.year}년` : null, h.genres.map(genreLabel).join(" · ")].filter(Boolean).join(" · ")}
                    </p>
                    {h.cast && <p className="mt-1 text-xs text-muted">{h.cast.split(", ").slice(0, 5).join(", ")}</p>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="text-xs text-muted">
        이 정적 배포판에서는 브라우저 안에서 검색합니다. 기억 검색(의미 검색·그래프)은 서버 배포에서만 동작합니다.
      </p>
    </div>
  );
}
