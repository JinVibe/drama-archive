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

const json = { "Content-Type": "application/json" };

export const me = {
  profile: async (): Promise<Me> => {
    const res = await fetch("/api/v1/me", { credentials: "same-origin" });
    if (!res.ok) throw new Error(`me ${res.status}`);
    return res.json();
  },
  list: async (): Promise<DramaState[]> => {
    const res = await fetch("/api/v1/me/dramas", { credentials: "same-origin" });
    if (!res.ok) throw new Error(`me/dramas ${res.status}`);
    return (await res.json()).items;
  },
  state: async (dramaId: number): Promise<DramaState | null> => {
    const res = await fetch(`/api/v1/me/dramas/${dramaId}`, { credentials: "same-origin" });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`me/dramas/${dramaId} ${res.status}`);
    return res.json();
  },
  set: async (dramaId: number, status: WatchStatus): Promise<DramaState> => {
    const res = await fetch(`/api/v1/me/dramas/${dramaId}/status`, {
      method: "PUT",
      headers: json,
      credentials: "same-origin",
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`set status ${res.status}`);
    return res.json();
  },
  clear: async (dramaId: number): Promise<void> => {
    const res = await fetch(`/api/v1/me/dramas/${dramaId}/status`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    if (!res.ok && res.status !== 404) throw new Error(`clear status ${res.status}`);
  },
};

export const STATUS_LABEL: Record<WatchStatus, string> = {
  WATCHED: "봤어요",
  WATCHING: "보는 중",
  WANT_TO_WATCH: "보고 싶어요",
};
