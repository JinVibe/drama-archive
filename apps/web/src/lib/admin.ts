import "server-only";
import { cookies } from "next/headers";
import { timingSafeEqual } from "node:crypto";

/**
 * Interim admin gate (DM-104): one shared token in ADMIN_TOKEN, entered once at
 * /admin/login and kept in an HttpOnly cookie scoped to /admin. Replaced by
 * OAuth + RBAC when DM-401's social login lands. An empty ADMIN_TOKEN disables
 * every admin page rather than opening it.
 */
export const ADMIN_COOKIE = "dm_admin";
const DOMAIN_API = process.env.DOMAIN_API_URL ?? "http://localhost:8081";

export function adminToken(): string {
  return process.env.ADMIN_TOKEN ?? "";
}

export function tokenMatches(candidate: string | undefined): boolean {
  const expected = adminToken();
  if (!expected || !candidate || candidate.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(candidate), Buffer.from(expected));
}

export async function isAdmin(): Promise<boolean> {
  const jar = await cookies();
  return tokenMatches(jar.get(ADMIN_COOKIE)?.value);
}

export async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${DOMAIN_API}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...(init?.headers ?? {}), "X-Admin-Token": adminToken(), "Content-Type": "application/json" },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not a problem detail */
    }
    throw new Error(`admin API ${path}: ${detail}`);
  }
  return res.json();
}

export type Candidate = { canonicalId: number; name: string; slug?: string; birthDate?: string; works: string[] };
export type ReviewEntity = {
  kind: "persons" | "songs" | "artists" | "drama";
  key: string;
  incomingName: string;
  incomingBirthDate?: string;
  incomingContext?: string;
  decision: string;
  confidence?: number;
  signals: Record<string, unknown>;
  candidate?: Candidate;
};
export type ReviewItem = {
  stagingId: number;
  sourceCode: string;
  dramaTitle: string;
  dramaExternalId: string;
  createdAt: string;
  entities: ReviewEntity[];
};
export type ProblemItem = {
  stagingId: number;
  status: string;
  sourceCode: string;
  dramaTitle?: string;
  updatedAt: string;
  issues: { code: string; severity: string; message: string }[];
};
