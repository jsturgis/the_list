# The List

A weekly SF Bay Area music discovery site, published at **https://list.sturgis.me/**.
Every Friday, a GitHub Action ingests the formatted edition of [Steve List's](mailto:skoepke@stevelist.com)
curated list, enriches it, and rebuilds a static site on GitHub Pages. A GraphQL API is available for
exploring the data locally.

The List itself is also published each week as plain text (the original email, subscriber footer
removed) in a [public Google Drive folder](https://drive.google.com/drive/folders/1plFG_Zp0lVbYOnzkbmHJ2DFTzYC8q1gH?usp=share_link).

## What it does

1. **Ingests** the newest formatted edition (structured JSON: shows, venues, artists with genres and links)
   from a public Google Drive folder each Friday
2. **Parses** each show's details (prices, age restrictions, times, and flags: `*` recommended, `$` will
   sell out, etc.)
3. **Enriches** new venues with Google Maps Places (address, lat/lng, place ID), looks up genres on
   MusicBrainz for new bands the edition has none for, and keeps only image URLs and links that work
4. **Stores** shows, bands, venues, and acts in SQLite (Alembic-managed schema)
5. **Indexes** band and show embeddings in FAISS for Similar Bands (Ollama `nomic-embed-text`)
6. **Exports** the data to static JSON and builds an Astro static site with region, band, venue, genre,
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
| Frontend | Astro static site with React islands, Tailwind; Vitest, React Testing Library, MSW, Playwright |
| Hosting | GitHub Pages, built and deployed by GitHub Actions |

**Colours** come from the theme in `frontend/src/styles/globals.css`: semantic tokens (`bg-surface`, `text-ink-muted`,
`border-line`, `bg-accent`, `text-link`, `bg-danger-soft`, …) that switch with the system's light/dark setting.
Use them instead of palette classes like `text-zinc-500`, and don't add `dark:` colour variants; to change a colour,
change its token there. The streaming-service buttons (Spotify, SoundCloud, Bandcamp) keep their brand colours.

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

**Frontend data.** The site is built from static JSON exported from the database, not the API. Export it
into `frontend/export/` (gitignored; read at build time, not published) whenever the data changes, then run the
frontend:

```bash
docker compose run --rm -v "$PWD/frontend/export:/export" api python -m app.cli export --out /export
cd frontend && npm run dev     # http://localhost:3000/the_list/
```

The site is served from `/the_list/`, as on GitHub Pages. `npm run build` writes the static site to
`frontend/dist/`; `npm run preview` serves it under that path.

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
| `SUPABASE_URL` | (none) | Weekly Alerts: the Supabase project URL, `https://<ref>.supabase.co` (ADR 0003) |
| `SUPABASE_SERVICE_ROLE_KEY` | (none) | Weekly Alerts: the project's secret key (`sb_secret_…`); it reads every Saved Filter, so keep it to GitHub secrets and a local `.env` |
| `SITE_URL` | `https://list.sturgis.me` | Where links in the Alert emails point |

> **Drive setup**: install `scripts/drive-publisher.gs` as a Google Apps Script with a daily trigger. It moves formatted editions from your Drive root into a public folder (raw email exports into a private one) and keeps `latest.json` pointing at the newest edition and, when there is one, its enriched export (`San Francisco Area Music List for <date>.enriched.json`), which the ingest uses to fill in missing venue details, ticket links and artist images. Set `DRIVE_LATEST_FILE_ID` to that file's id. Add `scripts/gmail-exporter.gs` to the same project to also save the newest List email (footer stripped) to the [public folder](https://drive.google.com/drive/folders/1plFG_Zp0lVbYOnzkbmHJ2DFTzYC8q1gH?usp=share_link) as `.txt`.

> **Alerts dry run**: with the two Supabase settings in `backend/.env`, `docker compose run --rm api python -m app.cli alerts --dry-run`
> prints this week's Alert emails (one per person whose Saved Filters match Upcoming Shows) without sending anything.
> The Supabase schema is in `supabase/migrations/`, applied by hand in the SQL editor.

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
  src/
    pages/           # Astro pages: home, Show, Band and Venue pages, Alerts, 404
    layouts/         # the page shell: head, header, link behaviour script
    components/      # UI (React)
    lib/             # data loading, browser filtering, navigation, base path helper
  __tests__/
samples/             # sample edition JSON and the (redacted) email it came from
scripts/
  drive-publisher.gs # Google Apps Script that publishes editions to the public Drive folder
  gmail-exporter.gs  # Google Apps Script that saves the newest List email to that folder as .txt
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

The site is published at **https://list.sturgis.me/** as a static site on GitHub Pages (see
[ADR 0002](docs/adr/0002-static-site-on-github-pages.md)). The old address, https://jsturgis.github.io/the_list/,
redirects there.

- **Custom domain**: set in Settings → Pages, with a `CNAME` record `list` → `jsturgis.github.io` in the
  `sturgis.me` DNS. The build takes its base path and site URL from `actions/configure-pages`
  (`PAGES_BASE_PATH`, `PAGES_SITE_URL`): `""` and `https://list.sturgis.me` with the domain, `/the_list` and
  `https://jsturgis.github.io/the_list` without it. Local builds default to `/the_list`.

- **The `data` branch** is an orphan branch holding the SQLite database (`the_list.db`) and the FAISS
  index (`faiss/`). `main` never contains data files. It keeps only its newest 4 commits (the current
  data plus 3 to roll back to): after each ingest, older history is squashed into the oldest kept
  commit and the branch is force-pushed (`.github/scripts/prune-history.sh`).
- **The Deploy workflow** (`.github/workflows/deploy.yml`) has three stages:
  1. **Ingest**: runs `python -m app.cli ingest` against the `data` branch's database (with an Ollama
     service container for embeddings) and commits the changed database and index back to `data`.
  2. **Build and deploy**: checks out `main` and the `data` branch, runs `python -m app.cli export`,
     builds the static site and deploys it to Pages.
  3. **Alerts**: after a successful ingest and deploy only, runs `python -m app.cli alerts`. That emails
     each person whose Saved Filters match Upcoming Shows (see [Weekly Alerts](#weekly-alerts)). It never
     runs on deploy-only runs. If it fails, the site stays deployed and the run shows red.
- **When it runs**:
  - **Every Friday night**, cron `0 4 * * 6` (Saturday 04:00 UTC = Friday 9pm PDT / 8pm PST), after
    the Drive publisher updates `latest.json` between 6 and 7pm Pacific. Ingest, then deploy.
  - **By hand** from the Actions tab (**Deploy → Run workflow**) or `gh workflow run deploy.yml`.
    A manual run with ingest also sends Alerts (re-running the same day sends no one a second email).
    Tick **Skip ingestion** (`gh workflow run deploy.yml -f skip_ingest=true`) to rebuild from the
    existing data without sending Alerts.
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

## Weekly Alerts

People save the Shows list's filters as **Saved Filters** ("Setup Alert"), signing in with an emailed link.
After each Friday ingest they get one **Alert** email listing the Upcoming Shows that match (see
[ADR 0003](docs/adr/0003-saved-filter-alerts-on-supabase.md)). Accounts and Saved Filters live in Supabase;
emails go through Resend from `alerts@list.sturgis.me`.

- **Commands:**
  - `python -m app.cli alerts` sends this week's Alerts.
  - `--dry-run` prints them instead.
  - `--only you@example.com` sends just one person's, as a test.
- **One-time setup:**
  1. **Supabase project:** email sign-in on. Site URL `https://list.sturgis.me`. Redirect URLs
     `https://list.sturgis.me/alerts/**` and `http://localhost:3000/the_list/alerts/**`; the wildcards are
     needed because the sign-in link carries the filter to save. Run `supabase/migrations/*.sql` in
     order in the SQL editor.
  2. **Resend:** verify `list.sturgis.me` (its DKIM, SPF and DMARC records are in the `sturgis.me` DNS),
     and create sending-only API keys.
  3. **Supabase SMTP:** send through Resend (`smtp.resend.com`, port 465, user `resend`), from
     `alerts@list.sturgis.me`.
  4. **GitHub:**
     - secrets `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (the `sb_secret_…` key) and `RESEND_API_KEY`
     - variables `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key) and
       `ALERTS_FROM`. The Deploy workflow passes the first two to the build as `PUBLIC_SUPABASE_URL` and
       `PUBLIC_SUPABASE_ANON_KEY`; set those in `frontend/.env` to try sign-in locally.
- **Unsubscribe:** every Alert links to `/alerts/unsubscribe/?token=…`, which turns that person's
  Alerts off without signing in. People can also turn them off and on, or delete alerts, on `/alerts/`.
- **Privacy:** email addresses never enter the repository, the `data` branch or the logs. The job logs
  counts only.

## How ingestion works

```
Google Drive (public folder)
  └─ latest.json → newest formatted edition JSON
       └─ edition_shows()        → upsert-ready dict per show (details parsed, bands with genres/links)
            └─ Google Places     → only for venues not yet in the DB
            └─ MusicBrainz       → genres for new bands (not yet in the DB) the edition has none for
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
