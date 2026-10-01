# The List

A weekly SF Bay Area music discovery app. Ingests the formatted edition of [Steve List's](mailto:skoepke@stevelist.com) curated Friday list, enriches new venues, and serves them through a GraphQL API and Next.js frontend.

## What it does

1. **Ingests** the newest formatted edition (structured JSON: shows, venues, artists with genres and links) from a public Google Drive folder each Friday
2. **Parses** each show's details (prices, age restrictions, times, and flags: `*` recommended, `$` will sell out, etc.)
3. **Enriches** new venues via Google Maps Places API (address, lat/lng, place ID)
4. **Stores** shows, bands, venues, and acts in SQLite (Alembic-managed schema)
5. **Indexes** show embeddings in FAISS for similarity search (Ollama nomic-embed-text)
6. **Serves** a Strawberry GraphQL API over FastAPI
7. **Renders** a Next.js SSG frontend with region/date/genre filters

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Strawberry GraphQL |
| ORM / migrations | SQLAlchemy 2, Alembic |
| Database | SQLite (development), PostgreSQL (production) |
| Enrichment | MusicBrainz API, Google Maps Places API, Claude Haiku 4.5 |
| Embeddings | Ollama `nomic-embed-text` (dim=768) |
| Vector search | FAISS `IndexIDMap(IndexFlatL2)` |
| Source | Formatted edition JSON on Google Drive (public link, `latest.json` pointer) |
| Frontend | Next.js (SSG), React Testing Library, MSW |

## Local setup

### Docker (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env — set GOOGLE_MAPS_API_KEY and DRIVE_LATEST_FILE_ID

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

**Seed from the sample email** (bypasses enrichment):
```bash
docker compose exec api python -c "
import email as e, sys
sys.path.insert(0, '.')
from app.database import Base, SessionLocal, engine
from app.ingestion.parser import parse_email_body
from app.ingestion.upsert import upsert_shows

msg = e.message_from_bytes(open('/samples/San Francisco Area Music List for Friday, September 25th, 2026.eml','rb').read())
plain = next(p.get_payload(decode=True).decode('utf-8') for p in msg.walk() if p.get_content_type()=='text/plain')
raw = parse_email_body(plain)
enriched = [{**vars(r), 'genres':[], 'spotify_url':None, 'soundcloud_url':None, 'venue_website':None, 'address':None, 'latitude':None, 'longitude':None, 'google_place_id':None, 'ticket_url':None} for r in raw]
Base.metadata.create_all(bind=engine)
db = SessionLocal()
shows = upsert_shows(db, enriched)
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

---

### Without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# edit .env
```

Required env vars:

| Variable | Description |
|---|---|
| `DRIVE_LATEST_FILE_ID` | Drive file id of the public `latest.json` pointer |
| `GOOGLE_MAPS_API_KEY` | Google Maps Places API key (venue enrichment) |
| `DATABASE_URL` | SQLite or PostgreSQL URL (default: `sqlite:///./the_list.db`) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |

## Environment variables reference

### Required (no working default)

| Variable | Description |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Venue enrichment (address, lat/lng, place ID) |
| `DRIVE_LATEST_FILE_ID` | Drive file id of the public `latest.json` pointer (see below) |

### Required for production (defaults are dev-only)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./the_list.db` | Use a PostgreSQL URL in production |
| `FAISS_INDEX_PATH` | `./data/faiss` | Point to a persistent volume path (e.g. `/app/data/faiss`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama instance |

### Optional

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Only for the manual venue re-enrichment job (LLM name clean-up and Wikipedia descriptions); weekly ingestion makes no LLM calls |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Change only if swapping embedding models |
| `DATA_RETENTION_DAYS` | `90` | Shows older than this are hard-deleted |
| `MUSICBRAINZ_APP_NAME` | `the-list` | MusicBrainz rate-limit user-agent |
| `MUSICBRAINZ_APP_VERSION` | `0.1` | MusicBrainz rate-limit user-agent |
| `MUSICBRAINZ_CONTACT` | `https://github.com/jsturgis/the_list` | MusicBrainz rate-limit contact |

> **Drive setup**: install `scripts/drive-publisher.gs` as a Google Apps Script with a daily trigger. It moves formatted editions from your Drive root into a public folder (raw email exports into a private one) and keeps `latest.json` pointing at the newest edition. Set `DRIVE_LATEST_FILE_ID` to that file's id.

Run the tests:

```bash
python -m pytest
```

Start the API server (creates tables automatically on first boot):

```bash
uvicorn app.main:app --reload
```

GraphQL playground: http://localhost:8000/graphql

## Project structure

```
backend/
  app/
    ingestion/       # Email parser (T1) and upsert layer (T2)
    enrichment/      # MusicBrainz + Google Maps + LLM chain (T5)
    models/          # SQLAlchemy ORM models (Show, Band, Venue, Act)
    graphql/         # Strawberry types, queries, mutations
    embeddings/      # Ollama client + FAISS index
    pipeline/        # End-to-end wiring
    scheduler.py     # ingestion pipeline and daily maintenance (python -m app.cli ingest)
  tests/
    fixtures/        # Real .eml sample for parser tests
    test_parser.py   # 22 tests (parse_email_body seam)
    test_upsert.py   # 29 tests (upsert_shows seam)
  alembic/           # Database migrations
docs/
  adr/               # Architecture decision records
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
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
  index (`faiss/`). `main` never contains data files.
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
  the workflow.
- **Rolling back**: revert the bad commit on the `data` branch (`git revert <sha>` on a checkout of
  `data`, then push) and run the workflow.

## How ingestion works

```
Google Drive (public folder)
  └─ latest.json → newest formatted edition JSON
       └─ edition_shows()      → upsert-ready dict per show (details parsed, bands with genres/links)
            └─ Google Places   → only for venues not yet in the DB
                 └─ upsert_shows()  → Show rows in DB
                      └─ embed + index in FAISS
```

**Show identity** (upsert key): `(date, venue_id, door_time)` — re-running ingestion on the same email is idempotent.

**Bands**: DJs (`dj …`) and back-to-back sets (`… b2b …`) are excluded. The headliner (position 0) receives MusicBrainz enrichment; support acts get empty enrichment and are enriched when they headline.

**Data retention**: shows older than 90 days are hard-deleted.

## Issues / specs

- [#1 Backend MVP spec](https://github.com/jsturgis/the_list/issues/1)
- [#2 T1: Email parser](https://github.com/jsturgis/the_list/issues/2) ✅
- [#3 T3: GraphQL Show queries](https://github.com/jsturgis/the_list/issues/3) ✅
- [#4 T4: GraphQL Band + similarity](https://github.com/jsturgis/the_list/issues/4) ✅
- [#5 T2: Upsert layer](https://github.com/jsturgis/the_list/issues/5) ✅
- [#6 T5: Enrichment chain](https://github.com/jsturgis/the_list/issues/6) ✅
- [#7 T6: Gmail fetch + full pipeline](https://github.com/jsturgis/the_list/issues/7) ✅
- [#8 Frontend spec](https://github.com/jsturgis/the_list/issues/8)
