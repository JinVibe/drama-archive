import Link from "next/link";
import { api, BASE_PATH } from "@/lib/api";

// Server mode: the uncached fetches (lib/api.ts) make this page render per request, so
// `next build` never needs the Domain API. Static export: rendered once at build time.

export default async function HomePage() {
  const [years, broadcasters] = await Promise.all([api.years(), api.broadcasters()]);
  const total = years.reduce((n, y) => n + y.count, 0);
  const span = years.length ? `${years[years.length - 1].year}–${years[0].year}` : "";

  return (
    <div className="space-y-20">
      <section className="space-y-8 pt-6">
        <p className="eyebrow">Korean drama memory archive</p>
        <h1 className="display text-[clamp(2.75rem,8vw,6.5rem)]">
          그때 그 드라마,
          <br />
          <span className="text-accent">다시 만나기.</span>
        </h1>
        <p className="max-w-xl text-lg leading-relaxed text-muted">
          연도와 방송사로 지나온 시절의 드라마를 찾고, 봤던 작품을 기록해 나만의 연대기를 만드세요.
          제목이 기억나지 않아도 배우, OST, 줄거리 한 장면으로 찾아냅니다.
        </p>
        <form action={`${BASE_PATH}/search/`} className="flex max-w-xl gap-3">
          <input
            type="search"
            name="q"
            placeholder="예) 2016년쯤 겨울에 공유 나온 판타지"
            className="flex-1 border-b border-line-strong bg-transparent px-1 py-3 text-lg placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <button type="submit" className="btn btn-primary">
            검색
          </button>
        </form>
        {total > 0 && (
          <p className="text-sm text-muted">
            <span className="text-foreground">{total.toLocaleString()}</span>편 · {span} · {broadcasters.length}개 채널
          </p>
        )}
      </section>

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="eyebrow">Ⅰ · 연도별</h2>
          <span className="text-xs text-muted">{years.length}개 연도</span>
        </div>
        {years.length === 0 ? (
          <p className="text-muted">아직 등록된 작품이 없습니다.</p>
        ) : (
          <ul className="row-list">
            {years.map((y) => (
              <li key={y.year}>
                <Link href={`/years/${y.year}`} className="row-link group flex items-baseline gap-6 py-4 md:py-5">
                  <span className="display w-32 text-4xl tabular-nums group-hover:text-accent md:text-5xl">{y.year}</span>
                  <span className="text-sm text-muted">{y.count}편</span>
                  <span className="ml-auto text-sm text-muted transition group-hover:translate-x-1 group-hover:text-accent">→</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="eyebrow mb-4">채널</h2>
        <ul className="flex flex-wrap gap-2">
          {broadcasters.map((b) => (
            <li key={b.code}>
              <Link href={years[0] ? `/years/${years[0].year}?broadcaster=${b.code}` : "/"} className="btn inline-block">
                {b.nameKo}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
