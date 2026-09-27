"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { me, STATUS_LABEL, type DramaState, type WatchStatus } from "@/lib/client";
import { yearOf } from "@/lib/format";

const GROUPS: WatchStatus[] = ["WATCHED", "WATCHING", "WANT_TO_WATCH"];

/** User state is per-browser session, so it is fetched on the client and never cached. */
export function MyDramas() {
  const [items, setItems] = useState<DramaState[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    me.list().then(setItems).catch(() => setError(true));
  }, []);

  if (error) return <p className="text-muted">기록을 불러오지 못했어요.</p>;
  if (items === null) return <p className="text-muted">불러오는 중…</p>;
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

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-3 gap-2 text-center">
        {GROUPS.map((g) => (
          <div key={g} className="rounded-lg border border-line bg-card py-3">
            <div className="text-2xl font-semibold">{items.filter((s) => s.status === g).length}</div>
            <div className="text-xs text-muted">{STATUS_LABEL[g]}</div>
          </div>
        ))}
      </section>

      {years.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">내 연대기</h2>
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
            <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">{STATUS_LABEL[g]}</h2>
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
