# The List

A weekly SF Bay Area music discovery app. Ingests [Steve List's](mailto:skoepke@stevelist.com) curated Friday email, enriches shows with genre tags and venue data, and serves them through a GraphQL API and Next.js frontend.

## What it does

1. **Ingests** a quoted-printable plain-text email from Gmail each Friday
2. **Parses** dates, venues, bands, prices, age restrictions, and show flags (`*` recommended, `$` will sell out, etc.)
3. **Enriches** headlining bands via MusicBrainz (genres, Spotify/SoundCloud links) and venues via Google Maps Places API (address, lat/lng)
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
| Email | Gmail API (service account) |
| Frontend | Next.js (SSG), React Testing Library, MSW |

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy the env template and fill in your keys:

```bash
cp .env.example .env
```

Required env vars:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (enrichment fallback) |
| `GMAIL_CREDENTIALS_PATH` | Path to Gmail OAuth2 credentials JSON |
| `GMAIL_TOKEN_PATH` | Path to Gmail token JSON |
| `GOOGLE_MAPS_API_KEY` | Google Maps Places API key (venue enrichment) |
| `DATABASE_URL` | SQLite or PostgreSQL URL (default: `sqlite:///./the_list.db`) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |

Run the tests:

```bash
python -m pytest
```

Apply database migrations:

```bash
alembic upgrade head
```

Start the API server:

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
    scheduler.py     # APScheduler weekly job
  tests/
    fixtures/        # Real .eml sample for parser tests
    test_parser.py   # 22 tests (parse_email_body seam)
    test_upsert.py   # 29 tests (upsert_shows seam)
  alembic/           # Database migrations
docs/
  adr/               # Architecture decision records
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
```

## How ingestion works

```
Gmail API
  └─ fetch latest email from skoepke@stevelist.com
       └─ parse_email_body()   → list[RawShow]
            └─ enrich_show()   → enriched dict per show
                 └─ upsert_shows()  → Show rows in DB
                      └─ embed + index in FAISS
```

**Show identity** (upsert key): `(date, venue_id, door_time)` — re-running ingestion on the same email is idempotent.

**Bands**: DJs (`dj …`) and back-to-back sets (`… b2b …`) are excluded. The headliner (position 0) receives MusicBrainz enrichment; support acts get empty enrichment and are enriched when they headline.

**Data retention**: shows older than 90 days are hard-deleted.

## Issues / specs

- [#1 Backend MVP spec](https://github.com/jeffsturgis/the_list/issues/1)
- [#2 T1: Email parser](https://github.com/jeffsturgis/the_list/issues/2) ✅
- [#3 T3: GraphQL Show queries](https://github.com/jeffsturgis/the_list/issues/3)
- [#4 T4: GraphQL Band + similarity](https://github.com/jeffsturgis/the_list/issues/4)
- [#5 T2: Upsert layer](https://github.com/jeffsturgis/the_list/issues/5) ✅
- [#6 T5: Enrichment chain](https://github.com/jeffsturgis/the_list/issues/6)
- [#7 T6: Gmail fetch + full pipeline](https://github.com/jeffsturgis/the_list/issues/7)
- [#8 Frontend spec](https://github.com/jeffsturgis/the_list/issues/8)
