---
title: How ingestion works
description: From the Drive edition to Shows, Bands and Venues in the database.
---

`python -m app.cli ingest` runs the steps below (`app/scheduler.py`). The services are the source of truth for a
new Band; the edition is used only when every service has nothing. A Band or Venue already in the database isn't
looked up again at ingest. The Backfill workflow looks stored Bands up again (see
[Deployment](deployment.md#the-backfill-workflow)); a Venue is refreshed by hand (see
[Fixing data by hand](#fixing-data-by-hand)). For how this fits into the weekly
run, see [Architecture](architecture.md#offline-jobs).

```mermaid
flowchart TD
  accTitle: The ingest, step by step
  accDescr: Daily maintenance, then the newest edition from Drive is mapped to Shows. New Venues are looked up on Google Places. Joint billings are split, Band corrections applied, and new Bands looked up on MusicBrainz, then for a photo on Wikimedia Commons, Discogs and Bandcamp, and for genres on Last.fm and Discogs, then MusicBrainz's free-form tags. Image URLs and links are checked; Shows, Venues, Bands and Acts are upserted; Band photos are stored; Shows and headliners are embedded and indexed in FAISS.
  maintenance["Daily maintenance<br/>mark Past Shows,<br/>delete old ones"]
  drive[("Google Drive<br/>latest.json → edition JSON")]
  map["edition_shows()<br/>one dict per Show"]
  places["Google Places<br/>new Venues only"]
  joint["joint_bands.py<br/>split joint billings"]
  corrections["band_corrections.py"]
  mb["MusicBrainz<br/>new Bands only"]
  photo["Photo: Wikimedia Commons,<br/>else Discogs, else Bandcamp,<br/>else the edition's"]
  genres["Genres: MusicBrainz, else<br/>Last.fm, else Discogs, else<br/>MusicBrainz's tags, else the edition's"]
  filter["genre_filter.py<br/>keeps only genres"]
  checks["images.py, links.py<br/>check image URLs, links"]
  upsert["upsert_shows()<br/>Show, Venue, Band, Act rows"]
  photos["band_photos.py<br/>store each photo"]
  embed["batch_embed_and_index()<br/>Ollama → FAISS"]
  maintenance --> drive --> map
  map --> places & joint
  joint --> corrections --> mb
  mb --> photo & genres
  genres --> filter
  places & photo & filter --> checks
  checks --> upsert --> photos --> embed
```

- **The edition**: `latest.json` points at the newest edition and, when there is one, its enriched export, which
  fills in missing Venue details, ticket links and artist images (`app/ingestion/drive.py`, `enriched.py`).
- **Joint billings** ("Dying Fetus And Sanguisugabogg") become two Bands; a Band with "and" in its name ("Belle and
  Sebastian") stays one. MusicBrainz decides (`app/ingestion/joint_bands.py`).
- **A Band's correction** (`app/ingestion/band_corrections.py`) takes the place of the edition's genres and links.
- **MusicBrainz** finds the artist (the Bay Area one, when several share the name) and its links.
- **A Band's photo** is its Wikimedia Commons photo, found through MusicBrainz's Wikidata link and kept with its
  credit (`app/ingestion/wikimedia.py`); else its Discogs photo (`discogs.py`); else the band photo on its Bandcamp
  page (`bandcamp.py`); and only then the edition's. **Members** come from Discogs.
- **Genres** are MusicBrainz's curated ones, else Last.fm's tags (`app/ingestion/lastfm.py`), else Discogs' genres
  and styles (`app/ingestion/discogs.py`), else MusicBrainz's free-form tags, and only then the edition's.
  `genre_filter.py` keeps only genres: the `tev1:0.8b` model on Ollama judges a tag it hasn't seen.
- **Image URLs** are kept, repaired (Wikimedia paths) or dropped; links that don't work are dropped.
- **Band photos** still at a remote URL are downloaded, resized to ≤800px WebP and saved to the images folder
  (`app/ingestion/band_photos.py`), with a focal point from the faces in them (`photo_focus.py`).
- **Embeddings** (`nomic-embed-text` on Ollama) of each Show and its headliner go into the FAISS indices.

**Show identity** (upsert key): `(date, venue_id, door_time)`. Re-running ingestion on the same edition
is idempotent.

**Bands**: DJs (`dj …`) and back-to-back sets (`… b2b …`) are excluded. Band details from the edition
only fill empty fields, so corrections made in the database aren't overwritten.

**Data retention**: shows older than `DATA_RETENTION_DAYS` (90) are hard-deleted by the daily maintenance
that runs before each ingest.

## Fixing data by hand

These change the database, so to fix the published site run them against a checkout of the `data` branch, then
commit it and redeploy, as [Deployment](deployment.md#changing-the-data-by-hand) describes. The scripts are dry runs
unless given `--apply`.

- **A Band matched to the wrong artist**, or with the wrong genres or links: add a correction for it to
  `app/ingestion/band_corrections.py` (its MusicBrainz artist, or that it's never matched by name, and the genres
  and links to use). Then look it up again: `python -m app.cli backfill --redo "<name>"`, or the Backfill
  workflow's **redo** input.
- **A tag that isn't a genre** (or one wrongly dropped): edit its row in the `genre_tags` table (`is_genre`, and
  `decided_by = 'hand'`), then run the backfill with `--recheck-genres`.
- **A Venue's details** (address, coordinates, description): the `refreshVenueEnrichment` GraphQL mutation on the
  local API looks one Venue up again (`venueId`), or every Venue without one, overwriting what's stored. It's the
  only job that uses `ANTHROPIC_API_KEY`, to tidy the name and write the description.
- **The same Band stored twice** under different spellings: `python -m app.ingestion.dedupe_bands`. Then
  `python -m app.ingestion.index_stored_vectors`, which adds any stored vector the FAISS indexes are missing, so
  the kept Band still comes up as a Similar Band.
- **The same Venue stored twice**: `python -m app.ingestion.dedupe_venues`.
- **A Band name that includes a set time or show details** ("The Coverups (2:30pm)"):
  `python -m app.ingestion.clean_band_names`.
