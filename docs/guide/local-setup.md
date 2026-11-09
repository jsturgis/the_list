---
title: Local setup
description: Run the backend, an ingest and the site on your own machine.
order: 2
---

## Docker (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env: set GOOGLE_MAPS_API_KEY and DRIVE_LATEST_FILE_ID

docker compose up --build
```

The API starts at `http://localhost:8000/graphql`. Tables are created automatically on first boot. The SQLite DB and FAISS indices are persisted in `./data/` on the host.

**Pull the Ollama models** (one-time, needed for the full pipeline): the embedding model, and the genre model that
judges whether a tag is a genre (`app/ingestion/genre_filter.py`; needs Ollama 0.35 or later, so
`docker compose pull ollama` first if yours is older):
```bash
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull tev1:0.8b
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

**Frontend data.** The site is built from static JSON exported from the database, not the API. Export it
into `frontend/export/` (gitignored; read at build time, not published) whenever the data changes, then run the
frontend:

```bash
docker compose run --rm -v "$PWD/frontend/export:/export" api python -m app.cli export --out /export
rm -rf frontend/public/images && cp -R data/images frontend/public/images   # Band photos, if any
cd frontend && npm run dev     # http://localhost:3000/the_list/
```

The site is served from `/the_list/`, as on GitHub Pages. `npm run build` writes the static site to
`frontend/dist/`; `npm run preview` serves it under that path.

Backend tests, in a throwaway container with the working tree mounted:

```bash
docker compose run --rm --no-deps -v "$PWD/backend:/src" -w /src api \
  sh -c "pip install -q -r requirements-dev.txt; python -m pytest -q"
```

Frontend checks (the same ones CI runs):

```bash
cd frontend && npm test && npm run typecheck && npm run lint
```

## Without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# edit .env: see Configuration (docs/guide/configuration.md)
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
