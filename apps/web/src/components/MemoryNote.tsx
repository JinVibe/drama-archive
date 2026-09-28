"use client";

import { useEffect, useState } from "react";
import { me } from "@/lib/client";

/** One private line of memory per drama. Saved through the same anonymous session as 봤어요. */
export function MemoryNote({ dramaId }: { dramaId: number }) {
  const [saved, setSaved] = useState<string | null | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    me.note(dramaId)
      .then((n) => alive && setSaved(n?.body ?? null))
      .catch(() => alive && setSaved(null));
    return () => {
      alive = false;
    };
  }, [dramaId]);

  async function save() {
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      const n = await me.setNote(dramaId, body);
      setSaved(n.body);
      setEditing(false);
    } catch {
      setError("저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    try {
      await me.clearNote(dramaId);
      setSaved(null);
      setDraft("");
      setEditing(false);
    } catch {
      setError("삭제하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  if (saved === undefined) return null;

  if (!editing) {
    return (
      <div className="text-sm">
        {saved ? (
          <blockquote className="rounded-md border-l-4 border-accent bg-card px-3 py-2">
            <p className="whitespace-pre-wrap">{saved}</p>
            <div className="mt-1 flex gap-3 text-xs text-muted">
              <span>나만 볼 수 있어요</span>
              <button type="button" className="hover:text-accent" onClick={() => { setDraft(saved); setEditing(true); }}>
                수정
              </button>
              <button type="button" className="hover:text-accent" onClick={remove} disabled={busy}>
                삭제
              </button>
            </div>
          </blockquote>
        ) : (
          <button type="button" className="text-muted hover:text-accent" onClick={() => setEditing(true)}>
            + 이 드라마에 대한 추억 한 줄 남기기
          </button>
        )}
      </div>
    );
  }

  return (
    <form
      className="space-y-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={500}
        rows={3}
        autoFocus
        placeholder="예) 고3 수능 끝나고 가족이랑 같이 봤다."
        className="w-full rounded-md border border-line bg-card px-3 py-2 focus:border-accent focus:outline-none"
      />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="rounded-md bg-accent px-3 py-1.5 text-accent-fg disabled:opacity-60"
        >
          저장
        </button>
        <button type="button" className="text-muted hover:text-foreground" onClick={() => setEditing(false)}>
          취소
        </button>
        <span className="ml-auto text-xs text-muted">{draft.length}/500 · 비공개</span>
      </div>
      {error && <p className="text-xs text-accent">{error}</p>}
    </form>
  );
}
