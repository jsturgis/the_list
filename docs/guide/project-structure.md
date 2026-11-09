---
title: Project structure
description: Where things live in the repository.
order: 7
---

```
backend/
  app/
    cli.py           # python -m app.cli ingest | export | alerts | backfill | photo-focus
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
    pages/           # Astro pages: home, Show, Band and Venue pages, Alerts, Docs, 404
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
  guide/             # these docs, rendered on the site at /docs/ (frontend/src/pages/docs)
  agents/            # Agent skill docs (issue tracker, triage labels, domain)
.github/workflows/   # backend and frontend tests, Deploy (weekly ingest + Pages)
```
