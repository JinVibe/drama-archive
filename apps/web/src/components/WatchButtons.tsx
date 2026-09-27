"use client";

import { useEffect, useState } from "react";
import { me, STATUS_LABEL, type WatchStatus } from "@/lib/client";

const ORDER: WatchStatus[] = ["WATCHED", "WATCHING", "WANT_TO_WATCH"];

/**
 * 봤어요 / 보는 중 / 보고 싶어요. Works without login: the first click creates an
 * anonymous session (cookie set by the Domain API through the /api rewrite).
 */
export function WatchButtons({ dramaId }: { dramaId: number }) {
  const [status, setStatus] = useState<WatchStatus | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    me.state(dramaId)
      .then((s) => alive && setStatus(s?.status ?? null))
      .catch(() => alive && setStatus(null));
    return () => {
      alive = false;
    };
  }, [dramaId]);

  async function toggle(next: WatchStatus) {
    if (busy) return;
    setBusy(true);
    setError(null);
    const prev = status;
    try {
      if (status === next) {
        setStatus(null);
        await me.clear(dramaId);
      } else {
        setStatus(next);
        await me.set(dramaId, next);
      }
    } catch {
      setStatus(prev);
      setError("저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="시청 기록">
        {ORDER.map((s) => {
          const active = status === s;
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggle(s)}
              disabled={busy || status === undefined}
              aria-pressed={active}
              className={
                "rounded-full border px-4 py-1.5 text-sm transition disabled:opacity-60 " +
                (active
                  ? "border-accent bg-accent text-white"
                  : "border-line bg-card hover:border-accent hover:text-accent")
              }
            >
              {STATUS_LABEL[s]}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted">
        {error ?? "로그인 없이 바로 기록돼요. 다른 기기에서도 보려면 나중에 계정을 연결하세요."}
      </p>
    </div>
  );
}
