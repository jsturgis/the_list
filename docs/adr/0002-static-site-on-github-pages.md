# Static site on GitHub Pages, rebuilt by GitHub Actions

The List is published as a static site on GitHub Pages instead of running the FastAPI/GraphQL backend on a server. The data changes once a week (a new edition every Friday), so every page can be built ahead of time: an Actions workflow exports the database to JSON, builds the Next.js static export under `/the_list`, and deploys it. Filtering, infinite scroll and the Band modal run in the browser from the exported JSON. The SQLite database and FAISS index live on an orphan `data` branch rather than on a server's disk; each ingest commits the new versions there and the deploy reads them.

## Considered Options

- **VPS (or small cloud VM) running the API, Next.js server and Ollama**: live GraphQL queries and no build step per edition, but costs money every month, needs patching, backups and uptime monitoring, and is a lot of machinery for data that changes weekly.
- **Static site on GitHub Pages, rebuilt by Actions**: free, nothing to keep running, and the published site can't be broken by a down server. Chosen.

## Consequences

- The GraphQL API is still the way to explore data locally, but the published site never calls it; anything the site shows has to be in the export.
- Every page must exist at build time (`dynamicParams = false`); a Band or Show added between deploys has no page until the next one.
- The `data` branch grows by roughly a database's size per ingest. If that becomes a problem, squash its history; only the latest commit is used.
- Rolling back the site is reverting a `data` branch commit and redeploying.
