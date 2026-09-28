# web

Next.js 16 (App Router) public archive UI. See `docs/ARCHITECTURE.md` §4.1.

| Route | Renders |
|---|---|
| `/` | years with published dramas, broadcasters |
| `/years/[year]?broadcaster=` | year archive |
| `/dramas/[slug]` | detail: cast, crew, OST, official links, 봤어요 buttons |
| `/persons/[slug]` | filmography |
| `/my` | the browser's own watched list / timeline (client-rendered) |
| `/sitemap.xml` | public catalog only |
| `/admin/login`, `/admin/review`, `/admin/problems` | entity-resolution review queue and dead-letter view; gated by `ADMIN_TOKEN` (HttpOnly cookie scoped to `/admin`, 8h). Interim until OAuth + RBAC |

## How data flows

- Server Components call the Domain API directly (`DOMAIN_API_URL`) and revalidate every 60s (`lib/api.ts`).
- The browser only talks to **this origin**: `src/app/api/[...path]/route.ts` proxies `/api/*` to the
  Domain API at runtime (reads `DOMAIN_API_URL` per request, forwards cookies and `Set-Cookie`), so the
  `dm_uid` session cookie is first-party (ADR-011). User state is fetched client-side and never cached.
- Pages are rendered per request (`next build` never calls the Domain API); catalog fetches are cached
  for 60s at the fetch level, which is the ISR-equivalent here.
- A 301 from the Domain API (merged entity) becomes a redirect to the surviving slug.

## Run

```sh
npm install
DOMAIN_API_URL=http://localhost:8081 npm run dev   # http://localhost:3000
npm run lint && npm run build
# or inside compose:
docker compose up -d --build web
```

## Design

Dark editorial theme (`src/app/globals.css`): near-black surfaces, warm off-white type, one amber
accent, Pretendard, index rows instead of cards, roman-numeral section labels. Tokens are exposed to
Tailwind via `@theme inline`; component classes (`.row-link`, `.btn`, `.eyebrow`, `.display`) live in
`@layer components` so utilities can still override them.
