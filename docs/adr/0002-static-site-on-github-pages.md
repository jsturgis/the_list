# Static site on GitHub Pages, rebuilt by GitHub Actions

The List is published as a static site on GitHub Pages instead of running the FastAPI/GraphQL backend on a server. The data changes once a week (a new edition every Friday), so every page can be built ahead of time: an Actions workflow exports the database to JSON, builds the Astro site from it (ADR 0004) under the Pages base path, and deploys it. Show, Venue and Band pages are plain HTML. The home page has the first page of Shows in its HTML; filtering and infinite scroll run in the browser from `home-shows.json`, which the build derives from the export. The SQLite database and FAISS index live on an orphan `data` branch rather than on a server's disk; each ingest commits the new versions there and the deploy reads them.

## Considered Options

- **VPS (or small cloud VM) running the API, a server-rendered frontend and Ollama**: live GraphQL queries and no build step per edition, but costs money every month, needs patching, backups and uptime monitoring, and is a lot of machinery for data that changes weekly.
- **Static site on GitHub Pages, rebuilt by Actions**: free, nothing to keep running, and the published site can't be broken by a down server. Chosen.

## Consequences

- The GraphQL API is still the way to explore data locally, but the published site never calls it; anything the site shows has to be in the export.
- Every page must exist at build time: the Show, Venue and Band pages come from `getStaticPaths` over the export, so a Band or Show added between deploys has no page until the next one, and any other id gets the 404 page.
- Pages are built days before some visits, so anything that depends on today's date is decided in the browser: past Shows are dropped from lists there, in Bay Area time.
- The build reads the export from `frontend/public/data` and writes the site to `frontend/dist`, which the Deploy workflow uploads. The export files are copied into the published site too, though the site itself no longer fetches them.
- The `data` branch grows by roughly a database's size per ingest. If that becomes a problem, squash its history; only the latest commit is used.
- Rolling back the site is reverting a `data` branch commit and redeploying.
