# The List: frontend

The static site published at https://list.sturgis.me/, built with [Astro](https://astro.build) from the
database export. Pages are plain HTML. React runs only where a page is interactive: the home page's Shows
list and filters, and the Alerts pages. See ADR 0002 (static site on GitHub Pages) and ADR 0004 (Astro with
React islands).

## Setup

Node 22.12 or newer (Astro 7's minimum). From this directory:

```bash
npm ci
```

The site is built from the database export in `public/data/` (gitignored). Export it from the repository root
whenever the data changes (see the root README for the backend):

```bash
docker compose run --rm -v "$PWD/frontend/public:/public" api python -m app.cli export --out /public/data
```

## Develop

```bash
npm run dev       # http://localhost:3000/the_list/
```

The site is served under `/the_list/`, as on GitHub Pages without the custom domain. Port 3000 matters for
signing in: `http://localhost:3000/the_list/alerts/**` is on Supabase's redirect allow-list (ADR 0003). The
Alerts features appear only when the build has `PUBLIC_SUPABASE_URL` and `PUBLIC_SUPABASE_ANON_KEY`. To try them
locally, put the values of the repository variables `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` in `.env` under those names.

## Build

```bash
npm run build     # writes the static site to dist/
npm run preview   # serves dist/ under /the_list/
```

The Deploy workflow builds with `PAGES_BASE_PATH` and `PAGES_SITE_URL` from GitHub Pages: an empty base path
and https://list.sturgis.me with the custom domain. Locally they default to `/the_list` and
https://jsturgis.github.io/the_list. `SITE_DATA_DIR` builds from another export (the tests use
`e2e/fixtures/data`).

## Layout

```
src/
  pages/        # one Astro page per route; Show, Venue and Band pages come from getStaticPaths over the export
                # home-shows.json.ts: the home page's Shows, generated at build time
  layouts/      # the page shell: head, header, and the scripts below
  components/   # React components, rendered at build time; HomeShows, AlertsPage and UnsubscribePage are islands
  lib/
    siteData.server.ts  # build-time access to the export
    keepFilters.ts      # carries the Shows list's filters onto Venue and Back links
    pastShows.ts        # CSS that hides Shows dated before today; inlined in each page's <head>
    navigation.ts       # the URL's query in React (useQuery, replaceQuery)
    basePath.ts         # href(): a site path under the base path
  styles/globals.css    # Tailwind and the colour theme (see the root README)
```

## Checks

The same ones CI runs:

```bash
npm test          # Vitest: components, libs, and Astro pages (rendered with Astro's container API)
npm run typecheck # astro check: .astro, .ts and .tsx, tests included
npm run lint
npm run e2e       # Playwright smoke tests
```

## Smoke tests

`npm run e2e` runs the Playwright smoke tests in `e2e/` (`npm run e2e:ui` for the interactive runner). The first
time, install the browser with `npx playwright install chromium`.

The tests don't use your local export in `public/data`. `e2e/serve.sh` builds the site from the small fixture
dataset in `e2e/fixtures/data` (setting `SITE_DATA_DIR`), then serves it under `/the_list/` the way GitHub Pages
does. The browser clock is frozen at 2026-10-01 (`e2e/fixtures.ts`), so the fixture Shows never go out of date.
If you change the fixtures, update the counts and names in `e2e/smoke.spec.ts`.
