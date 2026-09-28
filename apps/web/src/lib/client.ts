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

/** Drama facts a client keeps next to the state (the static build has no API to look them up). */
export type DramaMeta = DramaState["drama"];

/**
 * Static export (GitHub Pages) has no Domain API behind it: the same interface backed
 * by localStorage, so 봤어요/추억 한 줄 still work — in this browser only.
 */
const LS_KEY = "dm.local.v1";
type LocalStore = { states: Record<string, DramaState>; notes: Record<string, Note> };

function loadLocal(): LocalStore {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw) as LocalStore;
  } catch {
    /* private mode / blocked storage: fall through to an empty store */
  }
  return { states: {}, notes: {} };
}

function saveLocal(store: LocalStore) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(store));
  } catch {
    /* ignore: the UI already shows the optimistic state */
  }
}

const local = {
  profile: async (): Promise<Me> => ({ anonymous: true, displayName: "이 브라우저" }),
  list: async (): Promise<DramaState[]> =>
    Object.values(loadLocal().states).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1)),
  timeline: async (): Promise<Timeline> => {
    const states = Object.values(loadLocal().states);
    const byStatus = { WATCHED: 0, WATCHING: 0, WANT_TO_WATCH: 0 } as Record<WatchStatus, number>;
    const byYear = new Map<number, number>();
    const byBc = new Map<string, number>();
    for (const s of states) {
      byStatus[s.status] += 1;
      if (s.status !== "WATCHED") continue;
      const y = s.drama.startDate ? Number(s.drama.startDate.slice(0, 4)) : undefined;
      if (y) byYear.set(y, (byYear.get(y) ?? 0) + 1);
      if (s.drama.broadcasterCode) byBc.set(s.drama.broadcasterCode, (byBc.get(s.drama.broadcasterCode) ?? 0) + 1);
    }
    return {
      total: states.length,
      byStatus,
      byYear: [...byYear].map(([year, count]) => ({ year, count })).sort((a, b) => b.year - a.year),
      byBroadcaster: [...byBc]
        .map(([code, count]) => ({ code, nameKo: code.toUpperCase(), count }))
        .sort((a, b) => b.count - a.count),
      byGenre: [],
      topActors: [],
    };
  },
  state: async (dramaId: number): Promise<DramaState | null> => loadLocal().states[dramaId] ?? null,
  set: async (dramaId: number, status: WatchStatus, drama?: DramaMeta) => {
    const store = loadLocal();
    const prev = store.states[dramaId];
    const next: DramaState = {
      drama: drama ?? prev?.drama ?? { id: dramaId, slug: String(dramaId), titleKo: `#${dramaId}` },
      status,
      updatedAt: new Date().toISOString(),
    };
    store.states[dramaId] = next;
    saveLocal(store);
    return next;
  },
  clear: async (dramaId: number) => {
    const store = loadLocal();
    delete store.states[dramaId];
    saveLocal(store);
  },
  note: async (dramaId: number): Promise<Note | null> => loadLocal().notes[dramaId] ?? null,
  setNote: async (dramaId: number, body: string) => {
    const store = loadLocal();
    const note: Note = { dramaId, body, visibility: "PRIVATE", updatedAt: new Date().toISOString() };
    store.notes[dramaId] = note;
    saveLocal(store);
    return note;
  },
  clearNote: async (dramaId: number) => {
    const store = loadLocal();
    delete store.notes[dramaId];
    saveLocal(store);
  },
};

export const IS_STATIC = process.env.NEXT_PUBLIC_STATIC === "1";

const remote = {
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

// The remote client ignores the drama facts (the API knows them); the local one stores them.
export const me: typeof local = IS_STATIC ? local : remote;

export const STATUS_LABEL: Record<WatchStatus, string> = {
  WATCHED: "봤어요",
  WATCHING: "보는 중",
  WANT_TO_WATCH: "보고 싶어요",
};
