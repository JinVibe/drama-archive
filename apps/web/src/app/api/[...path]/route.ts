/**
 * Runtime proxy: /api/* -> Domain API. Keeps the dm_uid session cookie first-party
 * (ADR-011) without baking the upstream address into the build the way
 * next.config rewrites would; DOMAIN_API_URL is read per request.
 */
import type { NextRequest } from "next/server";

const BASE = () => process.env.DOMAIN_API_URL ?? "http://localhost:8081";

// Only what the Domain API needs; never forward hop-by-hop or host headers.
const FORWARD_REQUEST_HEADERS = ["accept", "content-type", "cookie", "accept-language"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "location", "cache-control"];

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const url = new URL(`${BASE()}/api/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
    cache: "no-store",
  });

  const out = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Session cookies are the whole point of this proxy.
  for (const cookie of upstream.headers.getSetCookie()) {
    out.append("set-cookie", cookie);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
