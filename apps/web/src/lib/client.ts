"use client";

/**
 * Browser-side calls for the user's own state. Same origin (/api proxy route), so
 * the dm_uid cookie rides along automatically; `credentials` is explicit anyway.
 */
export type WatchStatus = "WATCHED" | "WATCHING" | "WANT_TO_WATCH";

export type DramaState = {
  drama: { id: number; slug: string; titleKo: string; broadcasterCode?: string; startDate?: string };
  status: WatchStatus;
  rating?: number;
  firstWatchedYear?: number;
  updatedAt: string;
};

export type Me = { userId?: string; anonymous: boolean; displayName?: string };

export type Note = { dramaId: number; body: string; visibility: "PRIVATE" | "PUBLIC"; updatedAt: string };

export type Timeline = {
  total: number;
  byStatus: Record<WatchStatus, number>;
  byYear: { year: number; count: number }[];
  byBroadcaster: { code: string; nameKo: string; count: number }[];
  byGenre: { code: string; count: number }[];
  topActors: { slug: string; nameKo: string; count: number }[];
};

const json = { "Content-Type": "application/json" };
const opts: RequestInit = { credentials: "same-origin" };

async function getOrNull<T>(path: string): Promise<T | null> {
  const res = await fetch(path, opts);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, { ...opts, method: "PUT", headers: json, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`PUT ${path} ${res.status}`);
  return res.json();
}

async function del(path: string): Promise<void> {
  const res = await fetch(path, { ...opts, method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(`DELETE ${path} ${res.status}`);
}

export const me = {
  profile: async (): Promise<Me> => {
    const res = await fetch("/api/v1/me", opts);
    if (!res.ok) throw new Error(`me ${res.status}`);
    return res.json();
  },
  list: async (): Promise<DramaState[]> => {
    const res = await fetch("/api/v1/me/dramas", opts);
    if (!res.ok) throw new Error(`me/dramas ${res.status}`);
    return (await res.json()).items;
  },
  timeline: async (): Promise<Timeline> => {
    const res = await fetch("/api/v1/me/timeline", opts);
    if (!res.ok) throw new Error(`me/timeline ${res.status}`);
    return res.json();
  },
  state: (dramaId: number) => getOrNull<DramaState>(`/api/v1/me/dramas/${dramaId}`),
  set: (dramaId: number, status: WatchStatus) =>
    put<DramaState>(`/api/v1/me/dramas/${dramaId}/status`, { status }),
  clear: (dramaId: number) => del(`/api/v1/me/dramas/${dramaId}/status`),
  note: (dramaId: number) => getOrNull<Note>(`/api/v1/me/dramas/${dramaId}/note`),
  setNote: (dramaId: number, body: string) => put<Note>(`/api/v1/me/dramas/${dramaId}/note`, { body }),
  clearNote: (dramaId: number) => del(`/api/v1/me/dramas/${dramaId}/note`),
};

export const STATUS_LABEL: Record<WatchStatus, string> = {
  WATCHED: "봤어요",
  WATCHING: "보는 중",
  WANT_TO_WATCH: "보고 싶어요",
};
