---
title: How ingestion works
description: From the Drive edition to Shows, Bands and Venues in the database.
order: 5
---

`python -m app.cli ingest` runs the steps below (`app/scheduler.py`). The services are the source of truth for a
new Band; the edition is used only when every service has nothing. A Band or Venue already in the database isn't
looked up again (the Backfill workflow does that; see [Deployment](deployment.md)). For how this fits into the weekly
run, see [Architecture](architecture.md#offline-jobs).

```mermaid
flowchart TD
  accTitle: The ingest, step by step
  accDescr: Daily maintenance, then the newest edition from Drive is mapped to Shows. New Venues are looked up on Google Places. Joint billings are split, Band corrections applied, and new Bands looked up on MusicBrainz, then for a photo on Wikimedia Commons, Discogs and Bandcamp, and for genres on Last.fm and Discogs. Image URLs and links are checked; Shows, Venues, Bands and Acts are upserted; Band photos are stored; Shows and headliners are embedded and indexed in FAISS.
  maintenance["Daily maintenance<br/>mark Past Shows,<br/>delete old ones"]
  drive[("Google Drive<br/>latest.json → edition JSON")]
  map["edition_shows()<br/>one dict per Show"]
  places["Google Places<br/>new Venues only"]
  joint["joint_bands.py<br/>split joint billings"]
  corrections["band_corrections.py"]
  mb["MusicBrainz<br/>new Bands only"]
  photo["Photo: Wikimedia Commons,<br/>else Discogs, else Bandcamp,<br/>else the edition's"]
  genres["Genres: MusicBrainz,<br/>else Last.fm, else Discogs,<br/>else the edition's"]
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
- **MusicBrainz** finds the artist (the Bay Area one, when several share the name) and its links. Its Wikidata link
  leads to the Band's photo on Wikimedia Commons, with its credit (`app/ingestion/wikimedia.py`).
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
