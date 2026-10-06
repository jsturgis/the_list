#!/usr/bin/env bash
# Build the static site from the fixture data and serve it under /the_list/, as GitHub Pages does.
# Run by Playwright (playwright.config.ts webServer); run from the frontend directory.
set -euo pipefail

FIXTURES=e2e/fixtures/data
SITE=e2e/.site
PORT="${E2E_PORT:-4173}"

# Band photos, as the deploy copies the data branch's images folder into the site.
rm -rf public/images
cp -R "$FIXTURES/images" public/images

# Placeholder Supabase settings, so the Alerts features render (signed out); nothing contacts Supabase.
SITE_DATA_DIR="$FIXTURES" PUBLIC_SUPABASE_URL=https://e2e.invalid PUBLIC_SUPABASE_ANON_KEY=sb_publishable_e2e npx astro build

rm -rf "$SITE"
mkdir -p "$SITE"
cp -R dist "$SITE/the_list"

exec node e2e/server.mjs "$SITE" "$PORT"
