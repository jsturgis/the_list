---
title: Configuration
description: Environment variables for the backend.
---

Set these in `backend/.env` for local runs (`backend/.env.example` is a starting point). The Deploy workflow sets
its own from GitHub secrets and variables (see [Deployment](deployment.md#settings)). The names below are the
settings in `backend/app/config.py`.

## Required for an ingest

| Variable | Description |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Venue enrichment (address, lat/lng, place ID) |

The List itself needs no key: the ingest reads Steve's page, `LIST_URL` (default `https://stevelist.com/list`).

## Band lookups

Optional. MusicBrainz and Wikimedia Commons need no key.

| Variable | Description |
|---|---|
| `LASTFM_API_KEY` | Last.fm tags as new bands' genres when MusicBrainz has none. Without it Last.fm is skipped |
| `DISCOGS_CONSUMER_KEY`, `DISCOGS_CONSUMER_SECRET` | Discogs app credentials: new bands' members, photos, and genres after Last.fm's. Without them Discogs is skipped |
| `MUSICBRAINZ_APP_NAME` | MusicBrainz user-agent. Default `the-list` |
| `MUSICBRAINZ_APP_VERSION` | MusicBrainz user-agent. Default `0.1` |
| `MUSICBRAINZ_CONTACT` | MusicBrainz user-agent contact. Default `https://github.com/jsturgis/the_list` |

## Paths and services

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./the_list.db` | SQLite URL; Docker Compose sets `sqlite:////app/data/the_list.db` |
| `FAISS_INDEX_PATH` | `./data/faiss` | Docker Compose sets `/app/data/faiss` |
| `IMAGES_PATH` | `./data/images` | Band photos saved at ingest (`bands/<id>-<hash>.webp`); Docker Compose's `data` volume holds them at `/app/data/images` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama instance; Docker Compose sets `http://ollama:11434` |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Change only if swapping embedding models (requires re-embedding everything) |
| `GENRE_MODEL` | `tev1:0.8b` | The Ollama model that judges whether a tag is a genre (`app/ingestion/genre_filter.py`); needs Ollama 0.35 or later |
| `GENRE_MODEL_THRESHOLD` | `0.5` | The probability from which the genre model's answer counts as yes |

## Weekly Alerts

Only the `alerts` command needs these (see [Weekly Alerts](alerts.md)). A dry run needs the two Supabase settings
and no Resend key.

| Variable | Default | Notes |
|---|---|---|
| `SUPABASE_URL` | (none) | The Supabase project URL, `https://<ref>.supabase.co` (ADR 0003) |
| `SUPABASE_SERVICE_ROLE_KEY` | (none) | The project's secret key (`sb_secret_…`); it reads every Saved Filter, so keep it to GitHub secrets and a local `.env` |
| `RESEND_API_KEY` | (none) | A sending-only Resend key, to send the Alert emails |
| `ALERTS_FROM` | `The List <alerts@list.sturgis.me>` | The Alert emails' sender, on a domain verified in Resend |
| `SITE_URL` | `https://list.sturgis.me` | Where links in the Alert emails point |

## The maintainer's emails

The `notify-success` and `notify-failure` commands email the maintainer how the ingest went (see
[Deployment](deployment.md#the-maintainers-emails)). They send through Resend with `RESEND_API_KEY`, from
`ALERTS_FROM`, and link to `SITE_URL`; without either of `MAINTAINER_EMAIL` and `RESEND_API_KEY` they send nothing.

| Variable | Default | Notes |
|---|---|---|
| `MAINTAINER_EMAIL` | (none) | Who gets the emails about the ingest. In the Deploy workflow it's the `MAINTAINER_EMAIL` secret, so the address isn't in the public repository |

## Other

| Variable | Default | Notes |
|---|---|---|
| `DATA_RETENTION_DAYS` | `90` | Shows older than this are hard-deleted |
| `TIMEZONE` | `America/Los_Angeles` | Timezone for "today" and Upcoming vs Past |
| `ANTHROPIC_API_KEY` | (none) | Only for refreshing a Venue's details by hand (LLM name clean-up and Wikipedia descriptions; see [How ingestion works](ingestion.md#fixing-data-by-hand)); ingestion makes no LLM calls |

The site's build has its own settings (`PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY`, `PAGES_BASE_PATH`,
`PAGES_SITE_URL`, `SITE_DATA_DIR`): see the
[frontend's README](https://github.com/jsturgis/the_list/blob/main/frontend/README.md).
