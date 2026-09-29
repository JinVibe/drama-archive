#!/usr/bin/env bash
# Build the public catalog as a static site and publish it to the gh-pages branch
# (GitHub Pages, project site: https://<owner>.github.io/<repo>/).
#
# Needs the local stack up (domain-api :8081, ai-api :8090 for the graph sections)
# and Docker. Server-only routes (/api proxy, /admin, /share, OG images) are left
# out of the static copy; the browser searches public/search-index.json instead of
# ai-api, and 봤어요/추억 live in localStorage.
#
#   apps/web/scripts/deploy-pages.sh            # build + push gh-pages
#   DRY_RUN=1 apps/web/scripts/deploy-pages.sh  # build only (apps/web/out)
set -euo pipefail

WEB="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$WEB/../.." && pwd)"
REPO_URL="$(git -C "$ROOT" remote get-url origin)"
REPO_NAME="$(basename -s .git "$REPO_URL")"
OWNER="$(basename "$(dirname "$REPO_URL")" | sed 's/.*://')"
BASE_PATH="${BASE_PATH:-/$REPO_NAME}"
SITE_URL="${SITE_URL:-https://$(echo "$OWNER" | tr '[:upper:]' '[:lower:]').github.io$BASE_PATH}"
DOMAIN_API_URL="${DOMAIN_API_URL:-http://localhost:8081}"
AI_API_URL="${AI_API_URL:-http://localhost:8090}"
NODE_IMAGE="${NODE_IMAGE:-node:22-bookworm}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
echo "==> staging copy of apps/web in $STAGE (without server-only routes)"
tar -C "$WEB" --exclude=node_modules --exclude=.next --exclude=out -cf - . | tar -C "$STAGE" -xf -
rm -rf "$STAGE/src/app/api" "$STAGE/src/app/admin" "$STAGE/src/app/share" \
       "$STAGE/src/app/dramas/[slug]/opengraph-image.tsx" "$STAGE/src/lib/admin.ts"
# Metadata routes must declare themselves static for `output: export`; in server mode
# the sitemap stays per-request, so this is added to the staged copy only.
for f in robots.ts sitemap.ts; do
  printf '\nexport const dynamic = "force-static";\n' >> "$STAGE/src/app/$f"
done
# Dynamic routes need the full list of params for `output: export`. Kept out of the
# sources on purpose: with generateStaticParams present, the server build would treat
# these routes as SSG and cache each page after its first render.
cat >> "$STAGE/src/app/years/[year]/page.tsx" <<'EOF'

export async function generateStaticParams() {
  return (await api.years()).map((y) => ({ year: String(y.year) }));
}
EOF
cat >> "$STAGE/src/app/dramas/[slug]/page.tsx" <<'EOF'

import { allDramas } from "@/lib/api";
export async function generateStaticParams() {
  return (await allDramas()).map((d) => ({ slug: d.slug }));
}
EOF
cat >> "$STAGE/src/app/persons/[slug]/page.tsx" <<'EOF'

import { allPersonSlugs } from "@/lib/api";
export async function generateStaticParams() {
  return (await allPersonSlugs()).map((slug) => ({ slug }));
}
EOF

echo "==> search index + static build ($SITE_URL)"
# Git Bash on Windows: docker needs a Windows path for the bind mount.
STAGE_MOUNT="$(cygpath -m "$STAGE" 2>/dev/null || echo "$STAGE")"
MSYS_NO_PATHCONV=1 docker run --rm --network host -v "$STAGE_MOUNT:/app" -w /app \
  -e STATIC_EXPORT=1 -e BASE_PATH="$BASE_PATH" -e SITE_URL="$SITE_URL" \
  -e DOMAIN_API_URL="$DOMAIN_API_URL" -e AI_API_URL="$AI_API_URL" \
  "$NODE_IMAGE" bash -c "npm ci --no-audit --no-fund --silent && node scripts/build-search-index.mjs && npx next build"

rm -rf "$WEB/out"
cp -r "$STAGE/out" "$WEB/out"
touch "$WEB/out/.nojekyll"
echo "==> $(find "$WEB/out" -name '*.html' | wc -l) html files in apps/web/out"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN=1: not publishing"
  exit 0
fi

echo "==> publishing to gh-pages"
# A throwaway worktree on a fresh orphan branch (a unique name: `--orphan gh-pages` fails
# once a local gh-pages exists, and then every git command below would hit the main
# worktree). The commit is pushed straight to origin/gh-pages; nothing touches main.
PUB="$(mktemp -d)"
TMP_BRANCH="pages-$(date -u +%Y%m%d%H%M%S)"
rmdir "$PUB"
git -C "$ROOT" worktree add --detach "$PUB" HEAD >/dev/null
(
  cd "$PUB" || exit 1
  git switch --orphan "$TMP_BRANCH" >/dev/null
  cp -r "$WEB/out/." .
  git add -A
  git -c user.name="deploy-pages" -c user.email="deploy-pages@users.noreply.github.com" \
    commit -qm "deploy: static catalog $(date -u +%Y-%m-%dT%H:%MZ) from $(git -C "$ROOT" rev-parse --short HEAD)"
  git push -f origin "HEAD:gh-pages"
)
git -C "$ROOT" worktree remove --force "$PUB"
git -C "$ROOT" branch -D "$TMP_BRANCH" >/dev/null 2>&1 || true
echo "==> pushed gh-pages. Site: $SITE_URL/ (enable Pages: Settings → Pages → Branch gh-pages / root)"
