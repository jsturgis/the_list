---
title: Configuration
description: Environment variables, and the Google Drive scripts that publish each edition.
order: 4
---

Set these in `backend/.env` for local runs. The Deploy workflow sets its own (see [Deployment](deployment.md)).

## Required (no working default)

| Variable | Description |
|---|---|
| `DRIVE_LATEST_FILE_ID` | Drive file id of the public `latest.json` pointer (see Drive setup below) |
| `GOOGLE_MAPS_API_KEY` | Venue enrichment (address, lat/lng, place ID) |
| `LASTFM_API_KEY` | Last.fm tags as new bands' genres when MusicBrainz has none (optional; without it Last.fm is skipped) |
| `DISCOGS_CONSUMER_KEY`, `DISCOGS_CONSUMER_SECRET` | Discogs app credentials: new bands' members, photos, and genres after Last.fm's (optional; without them Discogs is skipped) |

## Paths and services

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./the_list.db` | SQLite URL; Docker Compose sets `sqlite:////app/data/the_list.db` |
| `FAISS_INDEX_PATH` | `./data/faiss` | Docker Compose sets `/app/data/faiss` |
| `IMAGES_PATH` | `./data/images` | Band photos saved at ingest (`bands/<id>-<hash>.webp`); Docker Compose's `data` volume holds them at `/app/data/images` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama instance |

## Optional

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

## Drive setup

Install `scripts/drive-publisher.gs` as a Google Apps Script with a daily trigger. It moves formatted editions from your Drive root into a public folder (raw email exports into a private one) and keeps `latest.json` pointing at the newest edition and, when there is one, its enriched export (`San Francisco Area Music List for <date>.enriched.json`), which the ingest uses to fill in missing venue details, ticket links and artist images. Set `DRIVE_LATEST_FILE_ID` to that file's id. Add `scripts/gmail-exporter.gs` to the same project to also save the newest List email (footer stripped) to the [public folder](https://drive.google.com/drive/folders/1plFG_Zp0lVbYOnzkbmHJ2DFTzYC8q1gH?usp=share_link) as `.txt`.

When a publish points `latest.json` at a new edition, the script also dispatches the Deploy workflow on `main` (ingestion on) so that week's ingest starts right away instead of waiting for the Saturday cron. To enable this, create a fine-grained personal access token limited to this repository, with Actions read and write permission, and set it as the `GITHUB_TOKEN` script property (Project Settings → Script properties, in the Apps Script editor). Without a token, publishing still works; the dispatch is skipped and logged instead.
