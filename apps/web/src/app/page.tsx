import Link from "next/link";
import { api } from "@/lib/api";

// Rendered per request so `next build` never needs the Domain API; the fetches
// themselves are cached for CATALOG_REVALIDATE seconds (lib/api.ts).
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [years, broadcasters] = await Promise.all([api.years(), api.broadcasters()]);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">
          그때 그 드라마, <span className="text-accent">다시 만나기</span>
        </h1>
        <p className="mt-2 max-w-2xl text-muted">
          연도와 방송사로 지나온 시절의 드라마를 찾고, 봤던 작품을 기록해 나만의 드라마 연대기를
          만들어 보세요.
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">연도별</h2>
        {years.length === 0 ? (
          <p className="text-muted">아직 등록된 작품이 없습니다.</p>
        ) : (
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5 md:grid-cols-8">
            {years.map((y) => (
              <li key={y.year}>
                <Link
                  href={`/years/${y.year}`}
                  className="flex flex-col items-center rounded-lg border border-line bg-card py-3 transition hover:border-accent"
                >
                  <span className="text-lg font-semibold">{y.year}</span>
                  <span className="text-xs text-muted">{y.count}편</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">방송사</h2>
        <ul className="flex flex-wrap gap-2">
          {broadcasters.map((b) => (
            <li key={b.code}>
              <Link
                href={years[0] ? `/years/${years[0].year}?broadcaster=${b.code}` : "/"}
                className="rounded-full border border-line bg-card px-4 py-1.5 text-sm hover:border-accent"
              >
                {b.nameKo}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
