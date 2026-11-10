---
title: Overview
description: What The List does each week, and what it’s built with.
order: 1
---

## What it does

1. **Ingests** the newest formatted edition (structured JSON: shows, venues, artists with genres and links)
   from a public Google Drive folder each Friday
2. **Parses** each show's details (prices, age restrictions, times, and flags: `*` recommended, `$` will
   sell out, etc.)
3. **Enriches** new venues with Google Maps Places (address, lat/lng, place ID), takes new bands' genres,
   links and members from MusicBrainz, Last.fm and Discogs, the source of truth (the edition's are used only when every
   service has nothing), takes each band's photo from Wikimedia Commons, Discogs or its Bandcamp page, and keeps only
   image URLs and links that work
4. **Stores** shows, bands, venues, and acts in SQLite (Alembic-managed schema)
5. **Indexes** band and show embeddings in FAISS for Similar Bands (Ollama `nomic-embed-text`)
6. **Exports** the data to static JSON and builds an Astro static site, with a band-or-venue search and region,
   genre, date, price, age and free-only filters, all running in the browser
7. **Emails** each week's Alerts: the Upcoming Shows that match each person's Saved Filters (Supabase and Resend)
8. **Serves** a Strawberry GraphQL API over FastAPI, for local development only

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, Strawberry GraphQL |
| ORM / migrations | SQLAlchemy 2, Alembic |
| Database | SQLite (kept on the `data` branch in production) |
| Enrichment | Venues: Google Maps Places API. Bands: MusicBrainz, Last.fm and Discogs (genres, links, members), with photos from Wikimedia Commons, Discogs or Bandcamp. Claude Haiku 4.5 only for the manual venue re-enrichment job |
| Genre filter | Ollama `tev1:0.8b`, judging once whether a tag that isn't on MusicBrainz's genre list is a genre |
| Embeddings | Ollama `nomic-embed-text` (dim=768) |
| Vector search | FAISS `IndexIDMap(IndexFlatL2)` |
| Photo focal points | OpenCV's YuNet face detector (`opencv-python-headless`; the model, `face_detection_yunet_2023mar.onnx` from the [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), is MIT-licensed and vendored in `backend/app/ingestion/yunet/` with its licence) |
| Source | Formatted edition JSON on Google Drive (public link, `latest.json` pointer) |
| Frontend | Astro static site with React islands, Tailwind; Vitest, React Testing Library, MSW, Playwright |
| Hosting | GitHub Pages, built and deployed by GitHub Actions |

**Design:** [`DESIGN.md`](https://github.com/jsturgis/the_list/blob/main/DESIGN.md) describes the site's design system: the colour tokens (defined in
`frontend/src/styles/globals.css`, switching with the system's light/dark setting), the Figtree typeface, the type
scale and the component styles. Use the semantic tokens (`bg-surface`, `text-ink-muted`, `text-link`, …) rather than
palette classes or `dark:` variants; a test keeps `DESIGN.md` and the stylesheet in sync.
