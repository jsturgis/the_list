#!/usr/bin/env bash
# Build the static site from the fixture data and serve it under /the_list/, as GitHub Pages does.
# Run by Playwright (playwright.config.ts webServer); run from the frontend directory.
set -euo pipefail

FIXTURES=e2e/fixtures/data
SITE=e2e/.site
PORT="${E2E_PORT:-4173}"

SITE_DATA_DIR="$FIXTURES" npx astro build

# The build copies public/data (the local export, if any) into dist/; the browser must load the fixtures.
rm -rf "$SITE"
mkdir -p "$SITE"
cp -R dist "$SITE/the_list"
rm -rf "$SITE/the_list/data"
cp -R "$FIXTURES" "$SITE/the_list/data"

exec node e2e/server.mjs "$SITE" "$PORT"
