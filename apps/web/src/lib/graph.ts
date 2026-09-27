/**
 * Server-side reads of the graph read model through ai-api. Every call is optional:
 * when ai-api or Neo4j is down the page renders without the relationship sections
 * (docs/ARCHITECTURE.md §11).
 */
import { CATALOG_REVALIDATE } from "@/lib/api";

const AI_API = process.env.AI_API_URL ?? "http://localhost:8090";

export type Via = { id: number; name: string; slug: string; credit: string };
export type RelatedDrama = { id: number; slug: string; title: string; year?: number; via: Via[]; strength: number };
export type RelatedByArtist = { id: number; slug: string; title: string; year?: number; artists: { id: number; name: string }[] };
export type Collaborator = {
  id: number;
  name: string;
  slug: string;
  works: number;
  dramas: { id: number; slug: string; title: string }[];
};

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${AI_API}${path}`, {
      next: { revalidate: CATALOG_REVALIDATE },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const graph = {
  related: (dramaId: number) =>
    get<{ by_people: RelatedDrama[]; by_ost_artists: RelatedByArtist[] }>(
      `/v1/graph/dramas/${dramaId}/related?limit=8`,
    ),
  collaborators: (personId: number) =>
    get<{ collaborators: Collaborator[] }>(`/v1/graph/persons/${personId}/collaborators?limit=8`),
};
