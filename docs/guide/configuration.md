---
title: Configuration
description: Environment variables, and the Google Drive scripts that publish each edition.
---

Set these in `backend/.env` for local runs (`backend/.env.example` is a starting point). The Deploy workflow sets
its own from GitHub secrets and variables (see [Deployment](deployment.md#settings)). The names below are the
settings in `backend/app/config.py`.

## Required for an ingest

| Variable | Description |
|---|---|
| `DRIVE_LATEST_FILE_ID` | Drive file id of the public `latest.json` pointer (see [Drive setup](#drive-setup)) |
| `GOOGLE_MAPS_API_KEY` | Venue enrichment (address, lat/lng, place ID) |

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

## Other

| Variable | Default | Notes |
|---|---|---|
| `DATA_RETENTION_DAYS` | `90` | Shows older than this are hard-deleted |
| `TIMEZONE` | `America/Los_Angeles` | Timezone for "today" and Upcoming vs Past |
| `ANTHROPIC_API_KEY` | (none) | Only for refreshing a Venue's details by hand (LLM name clean-up and Wikipedia descriptions; see [How ingestion works](ingestion.md#fixing-data-by-hand)); ingestion makes no LLM calls |

The site's build has its own settings (`PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY`, `PAGES_BASE_PATH`,
`PAGES_SITE_URL`, `SITE_DATA_DIR`): see the
[frontend's README](https://github.com/jsturgis/the_list/blob/main/frontend/README.md).

## Drive setup

Each week two JSON files are saved to the Drive root of the Google account that receives Steve's email: the
**formatted edition** (`Bay Area & Santa Cruz Concert Events - <date>.json`, schema v2.0.0) and its **enriched
export** (`San Francisco Area Music List for <date>.enriched.json`). They're made outside this repository; `samples/`
has one of each. Two Google Apps Scripts in `scripts/` publish them where the ingest can read them without Google
credentials:

- `drive-publisher.gs` moves formatted editions and enriched exports into a public folder (raw email exports, and
  any file that still holds personal data, into a private one). It keeps `latest.json` in the public folder pointing
  at the newest edition and, when there is one, its enriched export, which the ingest uses to fill in missing venue
  details, ticket links and artist images.
- `gmail-exporter.gs` saves the newest List email (footer stripped) to the
  [public folder](https://drive.google.com/drive/folders/1plFG_Zp0lVbYOnzkbmHJ2DFTzYC8q1gH?usp=share_link) as `.txt`.

To install them:

1. Paste `drive-publisher.gs` into a new project at https://script.google.com. Add `gmail-exporter.gs` to the same
   project as a second file.
2. Run `publish` once and grant Drive access. It logs the `latest.json` file id: set `DRIVE_LATEST_FILE_ID` to it
   (in `backend/.env`, and as the repository variable).
3. Run `exportListEmail` once to grant Gmail access.
4. Run `installTrigger` once. It runs `publish` daily between 6 and 7pm Pacific; `publish` exports the email too.
5. To start the week's ingest right after publishing, create a fine-grained personal access token limited to this
   repository, with Actions read and write permission, and set it as the `GITHUB_TOKEN` script property (Project
   Settings → Script properties).

With the token, a publish that points `latest.json` at a new edition also dispatches the Deploy workflow on `main`
(ingestion on), so that week's ingest starts right away instead of waiting for the Saturday cron. Without a token,
publishing still works; the dispatch is skipped and logged instead.
