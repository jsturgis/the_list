---
title: Project structure
description: Where things live in the repository.
---

For how these parts work together, see the diagrams in [Architecture](architecture.md).

```
backend/
  app/
    cli.py           # python -m app.cli check | ingest | export | alerts | notify-success | notify-failure | backfill | photo-focus
    scheduler.py     # the ingest and daily maintenance (`cli ingest`), and the check for a changed List (`cli check`)
    export.py        # static JSON export for the frontend
    alerts.py        # the weekly Alert emails, from Saved Filters in Supabase, sent through Resend
    notifications.py # the maintainer's emails: each successful ingest, and two weeks of failures
    mailer.py        # sends an email through Resend (for alerts.py and notifications.py)
    catalog.py       # filter options, Similar Bands, latest edition's title (shared by API and export)
    band_links.py    # which of a Band's listening and social links the site shows, and in what order
    slugs.py         # Slugs for Band, Venue and Show page URLs
    config.py        # settings, from environment variables
    ingestion/       # Steve's page: fetch, parser, upsert; Band lookups (Last.fm, Discogs, Wikimedia Commons,
                     # Bandcamp), corrections, genre filter, photos; the backfill; clean-up scripts
    pipeline/        # Google Places and MusicBrainz lookups, embedding
    embeddings/      # Ollama client + FAISS indices
    models/          # SQLAlchemy ORM models (Show, Band, Venue, Act, IngestionRun, GenreTag)
    graphql/         # Strawberry types, queries, mutations (local only)
  tests/
  alembic/           # Database migrations
frontend/
  src/
    pages/           # Astro pages: home, Show, Band and Venue pages, Alerts, 404
    content.config.ts  # the docs collection: Starlight renders ../docs/guide/ at /docs/
    layouts/         # the page shell: head, header, link behaviour script
    components/      # UI (React)
    lib/             # data loading, browser filtering, navigation, base path helper
    styles/          # the colour tokens, the site's stylesheet (Tailwind) and the docs' theme (Starlight)
  __tests__/         # Vitest: components, libs and pages
  e2e/               # Playwright: smoke, accessibility and consistency tests, their fixtures, the screenshot script
supabase/
  migrations/        # the Saved Filters and Alert subscriptions schema, applied by hand in the SQL editor
docs/
  adr/               # Architecture decision records
  guide/             # these docs, rendered on the site at /docs/ by Starlight
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
.github/
  workflows/         # backend and frontend tests, Deploy (hourly check, ingest + Pages), Backfill
  scripts/           # prune-history.sh, which keeps the data branch to its newest 4 commits
CONTEXT.md           # the domain language: Show, Act, Band, Venue, Saved Filter, Alert…
DESIGN.md            # the site's design system
docker-compose.yml   # the backend (api) and Ollama, for local runs
```
