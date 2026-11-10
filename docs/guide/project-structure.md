---
title: Project structure
description: Where things live in the repository.
order: 8
---

For how these parts work together, see the diagrams in [Architecture](architecture.md).

```
backend/
  app/
    cli.py           # python -m app.cli ingest | export | alerts | backfill | photo-focus
    scheduler.py     # the ingest and daily maintenance (run by `cli ingest`)
    export.py        # static JSON export for the frontend
    alerts.py        # the weekly Alert emails, from Saved Filters in Supabase, sent through Resend
    catalog.py       # filter options, Similar Bands, latest subject (shared by API and export)
    band_links.py    # which of a Band's listening and social links the site shows, and in what order
    slugs.py         # Slugs for Band, Venue and Show page URLs
    config.py        # settings, from environment variables
    ingestion/       # Drive fetch, edition mapping, upsert; Band lookups (Last.fm, Discogs, Wikimedia Commons,
                     # Bandcamp), corrections, genre filter, photos; the backfill; clean-up scripts
    pipeline/        # Google Places and MusicBrainz lookups, embedding
    embeddings/      # Ollama client + FAISS indices
    models/          # SQLAlchemy ORM models (Show, Band, Venue, Act, IngestionRun, GenreTag)
    graphql/         # Strawberry types, queries, mutations (local only)
  tests/
  alembic/           # Database migrations
frontend/
  src/
    pages/           # Astro pages: home, Show, Band and Venue pages, Alerts, Docs, 404
    layouts/         # the page shell: head, header, link behaviour script
    components/      # UI (React)
    lib/             # data loading, browser filtering, navigation, base path helper
    styles/          # Tailwind and the colour theme
  __tests__/         # Vitest: components, libs and pages
  e2e/               # Playwright: smoke, accessibility and consistency tests, their fixtures, the screenshot script
supabase/
  migrations/        # the Saved Filters and Alert subscriptions schema, applied by hand in the SQL editor
samples/             # a sample edition, its enriched export, and the (redacted) email it came from
scripts/
  drive-publisher.gs # Google Apps Script that publishes editions to the public Drive folder
  gmail-exporter.gs  # Google Apps Script that saves the newest List email to that folder as .txt
docs/
  adr/               # Architecture decision records
  guide/             # these docs, rendered on the site at /docs/ (frontend/src/pages/docs)
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
.github/
  workflows/         # backend and frontend tests, Deploy (weekly ingest + Pages), Backfill
  scripts/           # prune-history.sh, which keeps the data branch to its newest 4 commits
CONTEXT.md           # the domain language: Show, Act, Band, Venue, Saved Filter, Alert…
DESIGN.md            # the site's design system
docker-compose.yml   # the backend (api) and Ollama, for local runs
```
