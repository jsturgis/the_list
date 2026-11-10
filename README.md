# The List

A weekly SF Bay Area music discovery site, published at **https://list.sturgis.me/**.
Every Friday, a GitHub Action ingests the formatted edition of [Steve List's](mailto:skoepke@stevelist.com)
curated list, enriches it with MusicBrainz, Last.fm, Discogs and Google Places, and rebuilds a static site on
GitHub Pages. People can save searches and get a weekly email of the Shows that match.

The List itself is also published each week as plain text (the original email, subscriber footer
removed) in a [public Google Drive folder](https://drive.google.com/drive/folders/1plFG_Zp0lVbYOnzkbmHJ2DFTzYC8q1gH?usp=share_link).

## Documentation

The full docs are on the site, at **https://list.sturgis.me/docs/**:

- [Overview](https://list.sturgis.me/docs/overview/): what it does, and the stack
- [Architecture](https://list.sturgis.me/docs/architecture/): diagrams of the site, the backend and the weekly jobs
- [Local setup](https://list.sturgis.me/docs/local-setup/): Docker, seeding, the frontend, database migrations
- [Configuration](https://list.sturgis.me/docs/configuration/): environment variables and the Drive scripts
- [How ingestion works](https://list.sturgis.me/docs/ingestion/)
- [Deployment](https://list.sturgis.me/docs/deployment/): the Deploy workflow, the `data` branch, backfills, rollbacks
- [Weekly Alerts](https://list.sturgis.me/docs/alerts/)
- [Project structure](https://list.sturgis.me/docs/project-structure/)

Their source is Markdown in [`docs/guide/`](docs/guide/), and they're readable on GitHub too. Other docs in the
repo: [`CONTEXT.md`](CONTEXT.md) (the domain language), [`DESIGN.md`](DESIGN.md) (the design system),
[`docs/adr/`](docs/adr/) (architecture decisions) and [`frontend/README.md`](frontend/README.md).

## Quick start

```bash
cp backend/.env.example backend/.env    # set GOOGLE_MAPS_API_KEY and DRIVE_LATEST_FILE_ID
docker compose up --build -d            # GraphQL API at http://localhost:8000/graphql
```

The database starts empty. Load some Shows first: either
[seed it from the sample edition](docs/guide/local-setup.md#seed-from-the-sample-edition) (no keys or network needed)
or [run an ingest](docs/guide/local-setup.md#run-an-ingest-by-hand). Then export the data and start the site
(Node 22.12 or newer):

```bash
docker compose run --rm -v "$PWD/frontend/export:/export" api python -m app.cli export --out /export
cd frontend && npm ci && npm run dev    # http://localhost:3000/the_list/
```

See [Local setup](docs/guide/local-setup.md) for the details.

## Tests

```bash
docker compose run --rm --no-deps -v "$PWD/backend:/src" -w /src api \
  sh -c "pip install -q -r requirements-dev.txt; python -m pytest -q"   # backend
cd frontend && npm test && npm run typecheck && npm run lint && npm run e2e   # frontend, as CI runs them
```

## Stack

Python 3.12 (FastAPI, Strawberry GraphQL, SQLAlchemy, SQLite), Ollama embeddings with FAISS, and an Astro static site
with React islands and Tailwind (the docs with Starlight), deployed to GitHub Pages by GitHub Actions. Saved searches and Alerts use Supabase
and Resend.
