/**
 * DM-405 share card: a PNG of the browser's own drama timeline, rendered on the
 * server from the session cookie. Never cached (it is personal), never indexed
 * (robots disallows nothing here because the URL is useless without the cookie).
 */
import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";
import { renderShareCard, type ShareCardData } from "@/components/ShareCard";

export const dynamic = "force-dynamic";

const BASE = () => process.env.DOMAIN_API_URL ?? "http://localhost:8081";

export async function GET(req: NextRequest) {
  const cookie = req.headers.get("cookie") ?? "";
  const [timeline, list] = await Promise.all([
    fetch(`${BASE()}/api/v1/me/timeline`, { headers: { cookie }, cache: "no-store" }).then((r) => r.json()),
    fetch(`${BASE()}/api/v1/me/dramas`, { headers: { cookie }, cache: "no-store" }).then((r) => r.json()),
  ]);

  const data: ShareCardData = {
    watched: timeline.byStatus?.WATCHED ?? 0,
    years: timeline.byYear ?? [],
    broadcasters: timeline.byBroadcaster ?? [],
    actors: timeline.topActors ?? [],
    titles: (list.items ?? [])
      .filter((s: { status: string }) => s.status === "WATCHED")
      .slice(0, 8)
      .map((s: { drama: { titleKo: string } }) => s.drama.titleKo),
  };

  return new ImageResponse(renderShareCard(data), {
    width: 1200,
    height: 630,
    headers: { "cache-control": "private, no-store" },
  });
}
