---
title: How ingestion works
description: From the Drive edition to Shows, Bands and Venues in the database.
order: 4
---

```
Google Drive (public folder)
  └─ latest.json → newest formatted edition JSON
       └─ edition_shows()        → upsert-ready dict per show (details parsed, bands with genres/links)
            └─ Google Places     → only for venues not yet in the DB
            └─ joint billings    → "Dying Fetus And Sanguisugabogg" becomes two bands, "Belle and Sebastian"
                                   stays one (app/ingestion/joint_bands.py, decided on MusicBrainz)
            └─ MusicBrainz       → genres and links for new bands (not yet in the DB), over the edition's;
                                   genres: MusicBrainz's curated ones, Last.fm's tags (app/ingestion/lastfm.py),
                                   Discogs' genres and styles (app/ingestion/discogs.py), MusicBrainz's free-form
                                   tags, and only then the edition's
                 └─ Wikimedia      → the band's photo on Commons through its Wikidata link, with its credit
                                     (app/ingestion/wikimedia.py); else its Discogs photo ("Photo via Discogs");
                                     only then the edition's
            └─ image URL check   → keep, repair (Wikimedia paths) or drop each image URL
                 └─ upsert_shows()   → Show, Venue, Band and Act rows
                      └─ band photos     → download each band photo still at a remote URL, resize to ≤800px
                                           WebP, save to the images folder (app/ingestion/band_photos.py),
                                           with its focal point from the faces in it (photo_focus.py)
                      └─ embed + index in FAISS
```

**Show identity** (upsert key): `(date, venue_id, door_time)`. Re-running ingestion on the same edition
is idempotent.

**Bands**: DJs (`dj …`) and back-to-back sets (`… b2b …`) are excluded. Band details from the edition
only fill empty fields, so corrections made in the database aren't overwritten.

**Data retention**: shows older than `DATA_RETENTION_DAYS` (90) are hard-deleted by the daily maintenance
that runs before each ingest.
