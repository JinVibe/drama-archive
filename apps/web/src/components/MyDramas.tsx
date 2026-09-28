"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IS_STATIC, me, STATUS_LABEL, type DramaState, type Timeline, type WatchStatus } from "@/lib/client";
import { genreLabel, yearOf } from "@/lib/format";

const GROUPS: WatchStatus[] = ["WATCHED", "WATCHING", "WANT_TO_WATCH"];

/** User state is per-browser session, so it is fetched on the client and never cached. */
export function MyDramas() {
  const [items, setItems] = useState<DramaState[] | null>(null);
  const [stats, setStats] = useState<Timeline | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([me.list(), me.timeline()])
      .then(([list, tl]) => {
        setItems(list);
        setStats(tl);
      })
      .catch(() => setError(true));
  }, []);

  if (error) return <p className="text-muted">기록을 불러오지 못했어요.</p>;
  if (items === null || stats === null) return <p className="text-muted">불러오는 중…</p>;
  if (items.length === 0) {
    return (
      <p className="text-muted">
        아직 기록이 없어요. 작품 페이지에서 <strong>봤어요</strong>를 눌러 보세요. 로그인은 필요 없습니다.
      </p>
    );
  }

  const byYear = items
    .filter((s) => s.status === "WATCHED")
    .reduce<Record<string, DramaState[]>>((acc, s) => {
      const y = String(yearOf(s.drama.startDate) ?? "연도 미상");
      (acc[y] ??= []).push(s);
      return acc;
    }, {});
  const years = Object.keys(byYear).sort((a, b) => (a < b ? 1 : -1));
  const watched = stats.byStatus.WATCHED;

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-3 gap-2 text-center">
        {GROUPS.map((g) => (
          <div key={g} className="rounded-lg border border-line bg-card py-3">
            <div className="display text-4xl tabular-nums">{stats.byStatus[g]}</div>
            <div className="text-xs text-muted">{STATUS_LABEL[g]}</div>
          </div>
        ))}
      </section>

      {watched > 0 && (
        <section className="grid gap-4 sm:grid-cols-3">
          <Stat title="방송사" rows={stats.byBroadcaster.map((b) => [b.nameKo, b.count])} total={watched} />
          <Stat title="장르" rows={stats.byGenre.slice(0, 6).map((g) => [genreLabel(g.code), g.count])} total={watched} />
          <div className="rounded-lg border border-line bg-card p-3">
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">많이 본 배우</h3>
            {stats.topActors.length === 0 ? (
              <p className="text-sm text-muted">—</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {stats.topActors.slice(0, 6).map((a) => (
                  <li key={a.slug} className="flex justify-between">
                    <Link href={`/persons/${a.slug}`} className="hover:text-accent">
                      {a.nameKo}
                    </Link>
                    <span className="text-muted">{a.count}편</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {watched > 0 && !IS_STATIC && (
        <a
          href="/share/card.png"
          target="_blank"
          rel="noopener"
          className="btn inline-block"
        >
          내 연대기 카드 이미지 만들기 →
        </a>
      )}

      {years.length > 0 && (
        <section>
          <h2 className="eyebrow mb-4">연도별</h2>
          <ol className="space-y-4">
            {years.map((y) => (
              <li key={y}>
                <div className="mb-1 text-lg font-semibold">{y}</div>
                <ul className="divide-y divide-line rounded-md border border-line bg-card">
                  {byYear[y].map((s) => (
                    <li key={s.drama.id}>
                      <Link href={`/dramas/${s.drama.slug}`} className="block px-3 py-2 text-sm hover:text-accent">
                        {s.drama.titleKo}
                        {s.drama.broadcasterCode && (
                          <span className="ml-2 text-xs uppercase text-muted">{s.drama.broadcasterCode}</span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>
      )}

      {GROUPS.filter((g) => g !== "WATCHED").map((g) => {
        const list = items.filter((s) => s.status === g);
        if (list.length === 0) return null;
        return (
          <section key={g}>
            <h2 className="eyebrow mb-4">{STATUS_LABEL[g]}</h2>
            <ul className="divide-y divide-line rounded-md border border-line bg-card">
              {list.map((s) => (
                <li key={s.drama.id}>
                  <Link href={`/dramas/${s.drama.slug}`} className="block px-3 py-2 text-sm hover:text-accent">
                    {s.drama.titleKo}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function Stat({ title, rows, total }: { title: string; rows: [string, number][]; total: number }) {
  return (
    <div className="rounded-lg border border-line bg-card p-3">
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">—</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {rows.map(([label, count]) => (
            <li key={label}>
              <div className="flex justify-between">
                <span>{label}</span>
                <span className="text-muted">{Math.round((count / total) * 100)}%</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded bg-line">
                <div className="h-1.5 rounded bg-accent" style={{ width: `${(count / total) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
