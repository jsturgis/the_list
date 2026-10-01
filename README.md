# The List

A weekly SF Bay Area music discovery site, published at **https://jsturgis.github.io/the_list/**.
Every Friday, a GitHub Action ingests the formatted edition of [Steve List's](mailto:skoepke@stevelist.com)
curated list, enriches it, and rebuilds a static site on GitHub Pages. A GraphQL API is available for
exploring the data locally.

## What it does

1. **Ingests** the newest formatted edition (structured JSON: shows, venues, artists with genres and links)
   from a public Google Drive folder each Friday
2. **Parses** each show's details (prices, age restrictions, times, and flags: `*` recommended, `$` will
   sell out, etc.)
3. **Enriches** new venues with Google Maps Places (address, lat/lng, place ID), looks up genres on
   MusicBrainz for bands the edition has none for, and keeps only image URLs that actually load
4. **Stores** shows, bands, venues, and acts in SQLite (Alembic-managed schema)
5. **Indexes** band and show embeddings in FAISS for Similar Bands (Ollama `nomic-embed-text`)
6. **Exports** the data to static JSON and builds a Next.js static site with region, band, venue, genre,
   date and free-only filters, all running in the browser
7. **Serves** a Strawberry GraphQL API over FastAPI, for local development only

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Strawberry GraphQL |
| ORM / migrations | SQLAlchemy 2, Alembic |
| Database | SQLite (kept on the `data` branch in production) |
| Enrichment | Google Maps Places API, MusicBrainz API; Claude Haiku 4.5 only for the manual venue re-enrichment job |
| Embeddings | Ollama `nomic-embed-text` (dim=768) |
| Vector search | FAISS `IndexIDMap(IndexFlatL2)` |
| Source | Formatted edition JSON on Google Drive (public link, `latest.json` pointer) |
| Frontend | Next.js static export, Tailwind; Vitest, React Testing Library, MSW |
| Hosting | GitHub Pages, built and deployed by GitHub Actions |

## Local setup

### Docker (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env: set GOOGLE_MAPS_API_KEY and DRIVE_LATEST_FILE_ID

docker compose up --build
```

The API starts at `http://localhost:8000/graphql`. Tables are created automatically on first boot. The SQLite DB and FAISS indices are persisted in `./data/` on the host.

**Pull the Ollama embedding model** (one-time, needed for the full pipeline):
```bash
docker compose exec ollama ollama pull nomic-embed-text
```

**Run an ingest by hand** (maintenance, then the newest edition from Drive; the API server doesn't
schedule anything, the weekly run is a GitHub Action):
```bash
docker compose exec api python -m app.cli ingest
```

**Seed from the sample edition** (no network calls: no Drive, Google Places, MusicBrainz or embeddings):
```bash
docker compose exec api python -c "
import json
from app.database import Base, SessionLocal, engine
from app.ingestion.edition import edition_shows
from app.ingestion.upsert import upsert_shows

doc = json.load(open('/samples/Bay Area & Santa Cruz Concert Events - September 25, 2026 (v2.0.0 Final).json'))
Base.metadata.create_all(bind=engine)
db = SessionLocal()
shows = upsert_shows(db, edition_shows(doc))
db.commit()
print(f'Upserted {len(shows)} shows')
db.close()
"
```

Then query at `http://localhost:8000/graphql`:
```graphql
{ shows(limit: 5) { date venue { name city } acts { band { name } } isRecommended } }
```

> If you have Ollama running locally already, remove the `ollama` service from `docker-compose.yml` and add `OLLAMA_BASE_URL=http://host.docker.internal:11434` to `.env`.

**Frontend data.** The site reads static JSON exported from the database, not the API. Export it
into `frontend/public/data/` (gitignored) whenever the data changes, then run the frontend:

```bash
docker compose run --rm -v "$PWD/frontend/public:/public" api python -m app.cli export --out /public/data
cd frontend && npm run dev     # http://localhost:3000/the_list/
```

The site is served from `/the_list/`, as on GitHub Pages. `npm run build` writes the static site to
`frontend/out/`; to try it locally, serve it under that path:

```bash
mkdir -p /tmp/site && ln -sfn "$PWD/out" /tmp/site/the_list && python3 -m http.server 8080 -d /tmp/site
# http://localhost:8080/the_list/
```

Frontend checks (the same ones CI runs):

```bash
cd frontend && npm test && npm run typecheck && npm run lint
```

---

### Without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# edit .env: see the environment variables reference below
```

Run the tests:

```bash
python -m pytest
```

Start the API server (creates tables automatically on first boot):

```bash
uvicorn app.main:app --reload
```

GraphQL playground: http://localhost:8000/graphql. You also need Ollama running locally with
`nomic-embed-text` pulled for a full ingest.

## Environment variables reference

Set these in `backend/.env` for local runs. The Deploy workflow sets its own (see [Deployment](#deployment)).

### Required (no working default)

| Variable | Description |
|---|---|
| `DRIVE_LATEST_FILE_ID` | Drive file id of the public `latest.json` pointer (see Drive setup below) |
| `GOOGLE_MAPS_API_KEY` | Venue enrichment (address, lat/lng, place ID) |

### Paths and services

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./the_list.db` | SQLite URL; Docker Compose sets `sqlite:////app/data/the_list.db` |
| `FAISS_INDEX_PATH` | `./data/faiss` | Docker Compose sets `/app/data/faiss` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama instance |

### Optional

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Only for the manual venue re-enrichment job (LLM name clean-up and Wikipedia descriptions); ingestion makes no LLM calls |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Change only if swapping embedding models (requires re-embedding everything) |
| `DATA_RETENTION_DAYS` | `90` | Shows older than this are hard-deleted |
| `TIMEZONE` | `America/Los_Angeles` | Timezone for "today" and Upcoming vs Past |
| `MUSICBRAINZ_APP_NAME` | `the-list` | MusicBrainz user-agent |
| `MUSICBRAINZ_APP_VERSION` | `0.1` | MusicBrainz user-agent |
| `MUSICBRAINZ_CONTACT` | `https://github.com/jsturgis/the_list` | MusicBrainz user-agent contact |

> **Drive setup**: install `scripts/drive-publisher.gs` as a Google Apps Script with a daily trigger. It moves formatted editions from your Drive root into a public folder (raw email exports into a private one) and keeps `latest.json` pointing at the newest edition. Set `DRIVE_LATEST_FILE_ID` to that file's id.

## Project structure

```
backend/
  app/
    cli.py           # python -m app.cli ingest | export
    scheduler.py     # ingestion pipeline and daily maintenance (run by `cli ingest`)
    export.py        # static JSON export for the frontend
    catalog.py       # filter options, Similar Bands, latest subject (shared by API and export)
    ingestion/       # Drive fetch, edition mapping, upsert, image URL checks, venue clean-up scripts
    pipeline/        # Google Places + MusicBrainz enrichment, embedding
    embeddings/      # Ollama client + FAISS indices
    models/          # SQLAlchemy ORM models (Show, Band, Venue, Act, IngestionRun)
    graphql/         # Strawberry types, queries, mutations
  tests/
  alembic/           # Database migrations
frontend/
  app/               # Next.js pages: home, Show, Band and Venue pages, not-found
  components/        # UI, including the client-side Band modal
  lib/               # data loading, browser filtering, base path helper
  __tests__/
samples/             # sample edition JSON and the (redacted) email it came from
scripts/
  drive-publisher.gs # Google Apps Script that publishes editions to the public Drive folder
docs/
  adr/               # Architecture decision records
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
.github/workflows/   # backend and frontend tests, Deploy (weekly ingest + Pages)
```

## Database migrations

The API creates missing tables on startup, but new columns need an Alembic migration. Alembic uses the
app's `DATABASE_URL`.

```bash
docker compose exec api alembic upgrade head
```

A database created by the app itself has no Alembic version yet. Mark it once, depending on which
models created it:

- **It already has the latest columns** (created by the current code): just record that it's up to date.
  Running `upgrade` here fails, because the columns already exist.

  ```bash
  docker compose exec api alembic stamp head
  ```

- **It's missing newer columns** (created by older code): mark it at the first migration, then upgrade.

  ```bash
  docker compose exec api alembic stamp 5b5092d5ef44
  docker compose exec api alembic upgrade head
  ```

Check with `docker compose exec api alembic current`: it should print the head revision.

## Deployment

The site is published at **https://jsturgis.github.io/the_list/** as a static site on GitHub Pages (see
[ADR 0002](docs/adr/0002-static-site-on-github-pages.md)).

- **The `data` branch** is an orphan branch holding the SQLite database (`the_list.db`) and the FAISS
  index (`faiss/`). `main` never contains data files. It keeps only its newest 4 commits (the current
  data plus 3 to roll back to): after each ingest, older history is squashed into the oldest kept
  commit and the branch is force-pushed (`.github/scripts/prune-history.sh`).
- **The Deploy workflow** (`.github/workflows/deploy.yml`) has two jobs:
  1. **Ingest**: runs `python -m app.cli ingest` against the `data` branch's database (with an Ollama
     service container for embeddings) and commits the changed database and index back to `data`.
  2. **Build and deploy**: checks out `main` and the `data` branch, runs `python -m app.cli export`,
     builds the static site and deploys it to Pages.
- **When it runs**:
  - **Every Friday night**, cron `0 4 * * 6` (Saturday 04:00 UTC = Friday 9pm PDT / 8pm PST), after
    the Drive publisher updates `latest.json` between 6 and 7pm Pacific. Ingest, then deploy.
  - **By hand** from the Actions tab (**Deploy → Run workflow**) or `gh workflow run deploy.yml`.
    Tick **Skip ingestion** (`gh workflow run deploy.yml -f skip_ingest=true`) to rebuild from the
    existing data.
  - **On pushes to `main`** that touch `frontend/` or `backend/app/`: deploy only, no ingest.
  - Only one run at a time.
- **A week with no new edition** still succeeds and redeploys (the run is recorded as `no_email`).
- **A failed ingest** fails the run: the `data` branch is left untouched and nothing is deployed.
  GitHub emails you about failed scheduled runs (Settings → Notifications → Actions).
- **Settings**: Pages source must be **GitHub Actions** (Settings → Pages). The ingest uses the
  `GOOGLE_MAPS_API_KEY` secret and the `DRIVE_LATEST_FILE_ID` repository variable (Settings → Secrets
  and variables → Actions). No Anthropic key: ingestion makes no LLM calls.
- **Updating the data by hand**: commit a new `the_list.db` and `faiss/` to the `data` branch, then run
  the workflow with **Skip ingestion**.
- **Rolling back**: revert the bad commit on the `data` branch (`git revert <sha>` on a checkout of
  `data`, then push) and run the workflow with **Skip ingestion**. Only the last 3 changes can be rolled
  back this way. The branch is rewritten when it's pruned, so fetch it fresh
  (`git fetch origin data && git reset --hard origin/data`) before committing to it by hand.

## How ingestion works

```
Google Drive (public folder)
  └─ latest.json → newest formatted edition JSON
       └─ edition_shows()        → upsert-ready dict per show (details parsed, bands with genres/links)
            └─ Google Places     → only for venues not yet in the DB
            └─ MusicBrainz       → genres for bands the edition has none for and the DB doesn't know
            └─ image URL check   → keep, repair (Wikimedia paths) or drop each image URL
                 └─ upsert_shows()   → Show, Venue, Band and Act rows
                      └─ embed + index in FAISS
```

**Show identity** (upsert key): `(date, venue_id, door_time)`. Re-running ingestion on the same edition
is idempotent.

**Bands**: DJs (`dj …`) and back-to-back sets (`… b2b …`) are excluded. Band details from the edition
only fill empty fields, so corrections made in the database aren't overwritten.

**Data retention**: shows older than `DATA_RETENTION_DAYS` (90) are hard-deleted by the daily maintenance
that runs before each ingest.

## Issues / specs

- [#1 Backend MVP spec](https://github.com/jsturgis/the_list/issues/1) (tickets #2–#7)
- [#8 Frontend MVP spec](https://github.com/jsturgis/the_list/issues/8)
- [#10 Static site on GitHub Pages, rebuilt weekly](https://github.com/jsturgis/the_list/issues/10) (tickets #11–#19)
