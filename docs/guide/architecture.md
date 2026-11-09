---
title: Architecture
description: Diagrams of the site, the backend and the weekly jobs, and how they fit together.
order: 2
---

The List has three parts. The **backend** (Python, in `backend/app`) ingests each week's edition into a SQLite
database and exports it to JSON. The **frontend** (Astro, in `frontend/src`) builds a static site from that export.
The **offline jobs** (GitHub Actions and two Google Apps Scripts) run the backend each week and publish the site to
GitHub Pages. Nothing runs on a server: the published site is static files, plus Supabase for sign-in and Saved
Filters (see [ADR 0002](https://github.com/jsturgis/the_list/blob/main/docs/adr/0002-static-site-on-github-pages.md)
and [ADR 0003](https://github.com/jsturgis/the_list/blob/main/docs/adr/0003-saved-filter-alerts-on-supabase.md)).

## Frontend

### At build time

`astro build` reads the export (`shows.json`, `venues.json`, `bands.json`, `meta.json`) once, through
`lib/siteData.server.ts`, and writes every page ahead of time. Each Show, Venue and Band page is built at its Slug,
and again at its numeric URL, which redirects to the Slug. The other pages (Alerts, Unsubscribe, 404,
`robots.txt` and the sitemap) need no data. The export itself isn't published.

```mermaid
flowchart TD
  accTitle: The site at build time
  accDescr: lib/siteData.server.ts reads the export JSON for the Shows list, the Show, Venue and Band pages, the .ics files and home-shows.json; lib/docs.ts turns the guides' Markdown into the docs pages. astro build writes every page to frontend/dist, with the Band photos, and the Deploy workflow uploads it to GitHub Pages.
  export[("frontend/export<br/>shows, venues, bands, meta")]
  guides[("docs/guide/*.md")]
  siteData["lib/siteData.server.ts"]
  docsLib["lib/docs.ts"]
  dataPages["Shows list, Show, Venue<br/>and Band pages, .ics files,<br/>home-shows.json"]
  docsPages["Docs pages"]
  photos[("Band photos<br/>data branch")]
  dist[("frontend/dist")]
  host["GitHub Pages"]
  export -->|"JSON"| siteData --> dataPages
  guides -->|"Markdown"| docsLib --> docsPages
  dataPages & docsPages -->|"astro build"| dist
  photos -->|"public/images"| dist
  dist -->|"upload-pages-artifact"| host
```

### In the browser

Pages arrive as finished HTML. React runs only in the islands, the parts that change in the browser
([ADR 0004](https://github.com/jsturgis/the_list/blob/main/docs/adr/0004-astro-with-react-islands.md)). Two small
scripts without React cover the rest: the inline `<head>` script hides Shows that have passed since the build, and
`lib/keepFilters` carries the Shows list's filters onto Venue links and the Back link. The browser talks to
Supabase directly; its row-level security keeps each person's Saved Filters private.

```mermaid
flowchart LR
  accTitle: The site in the browser
  accDescr: A page from GitHub Pages runs the inline past-Shows script, the keepFilters script and its React islands; docs pages with a diagram also load Mermaid. HomeShows fetches home-shows.json. HomeShows, AlertBell and AlertsPage call Supabase for sign-in and Saved Filters; UnsubscribePage calls its unsubscribe function.
  page["Page from<br/>GitHub Pages"]
  head["&lt;head&gt; script<br/>hides past Shows"]
  keep["lib/keepFilters<br/>filters onto links"]
  diagrams["lib/diagrams<br/>docs pages only"]
  subgraph islands ["React islands"]
    homeShows["HomeShows<br/>client:load"]
    bell["AlertBell<br/>client:idle"]
    alertsPage["AlertsPage<br/>client:only"]
    unsubscribe["UnsubscribePage<br/>client:only"]
  end
  homeJson[("home-shows.json")]
  supabase[("Supabase<br/>auth, saved_filters")]
  mermaid[("mermaid")]
  page --> head & keep & diagrams & islands
  diagrams -->|"import()"| mermaid
  homeShows -->|"fetch"| homeJson
  homeShows & bell & alertsPage --> supabase
  unsubscribe -->|"rpc"| supabase
```

## Backend

### Modules

Everything runs from the command line (`python -m app.cli`). The GraphQL API (FastAPI and Strawberry) is for
exploring the data locally; the published site never calls it. The export and the Alerts reuse its code (the
mappers and `query_shows` in `graphql/queries.py`), so they can't drift from what the API returns.

```mermaid
flowchart TD
  accTitle: The backend's modules
  accDescr: cli.py runs the ingest (scheduler.py) and the backfill, the export and the alerts. The ingest and the backfill call the services through ingestion/ and pipeline/, and embed with Ollama into FAISS. The export and the alerts reuse the GraphQL code, as does the local FastAPI app. Everything reads and writes SQLite through the SQLAlchemy models.
  cli["app/cli.py"]
  api["app/main.py<br/>FastAPI, local only"]
  jobs["scheduler.py,<br/>backfill.py"]
  exportPy["export.py"]
  alertsPy["alerts.py"]
  services["ingestion/,<br/>pipeline/"]
  embed["pipeline/<br/>embed.py"]
  gql["graphql/<br/>Strawberry"]
  catalog["catalog.py"]
  models["models/"]
  ollama["Ollama"]
  faiss[("FAISS")]
  db[("SQLite")]
  out[("export/<br/>*.json")]
  cli --> jobs & exportPy & alertsPy
  api --> gql
  jobs --> services & embed
  exportPy & alertsPy --> gql
  exportPy --> out
  gql --> catalog
  services & embed --> ollama
  embed & catalog --> faiss
  jobs & gql --> models
  models -->|"SQL via<br/>SQLAlchemy"| db
```

- `cli.py` has five commands: `ingest`, `export`, `alerts`, `backfill` and `photo-focus`.
- `ingestion/` and `pipeline/enrichment.py` call the services (Google Drive, Google Places, MusicBrainz, Last.fm,
  Discogs, Wikimedia Commons, Bandcamp). Ollama runs two models: `nomic-embed-text` for embeddings, and
  `tev1:0.8b`, which judges whether a new tag is a genre (`ingestion/genre_filter.py`).
- `catalog.py` holds the read-only queries the API and the export share: filter options, Similar Bands (nearest
  in the Band FAISS index) and the latest edition's subject.
- `ingestion/band_photos.py` saves Band photos to `images/` (≤800px WebP, with a focal point from the faces in
  each, `photo_focus.py`).
- `alerts.py` reads Supabase and sends through Resend (see [Offline jobs](#offline-jobs)).

### Data

The core entities (a few fields each), as the SQLAlchemy models in `backend/app/models/` store them. A Show is at one Venue and has
its Acts in order (position 0 is the headliner); each Act is one Band's appearance. A Band's and a Show's
`embedding` is also in its FAISS index, under its id. Two tables stand alone: `ingestion_runs` (one row per ingest,
with its counts) and `genre_tags` (whether a tag is a genre, as judged once).

```mermaid
erDiagram
  accTitle: The core entities
  accDescr: A Venue hosts many Shows. A Show has many Acts, in order. A Band appears as many Acts.
  VENUE ||--o{ SHOW : hosts
  SHOW ||--o{ ACT : "has, in order"
  BAND ||--o{ ACT : "appears as"
  VENUE {
    int id PK
    string name
    string city
    enum region
  }
  SHOW {
    int id PK
    date date
    int venue_id FK
    time door_time
    enum status
    bool is_recommended
  }
  ACT {
    int id PK
    int show_id FK
    int band_id FK
    int position "0: headliner"
  }
  BAND {
    int id PK
    string name UK
    list genres
    string image_url
    datetime enriched_at
  }
```

Saved Filters and Alert subscriptions aren't in this database: they live in Supabase (`saved_filters`,
`alert_subscriptions`; see [Weekly Alerts](alerts.md)).

## Offline jobs

### When the Deploy workflow runs

The Deploy workflow (`.github/workflows/deploy.yml`) has four jobs. An ingest happens only on the publisher's
dispatch, the cron and a manual run that doesn't skip it; Alerts go out only after an ingest. Runs share the
`pages` concurrency group with the Backfill workflow, so only one runs at a time.

- **The Drive publisher's dispatch**: when it points `latest.json` at a new edition, Friday between 6 and 7pm
  Pacific.
- **The cron**, a fallback: `37 6 * * 6`, Saturday 06:37 UTC (Friday 11:37pm PDT).
- **By hand**: Run workflow, or `gh workflow run deploy.yml`, with or without **Skip ingestion**.
- **A push to `main`** that touches the site, the backend's app or the guides.
- **The Backfill workflow**, after it commits to the `data` branch.

See [Deployment](deployment.md) for each.

```mermaid
flowchart TD
  accTitle: When the Deploy workflow runs
  accDescr: The Drive publisher's dispatch, the Friday-night cron and a manual run start the ingest job. A manual run that skips ingestion, a push to main and the Backfill workflow start at the build job. Build is followed by deploy, and deploy by alerts, but only after an ingest.
  dispatch["Publisher's<br/>dispatch"]
  cron["Cron<br/>fallback"]
  manual["By hand"]
  ingest["ingest<br/>cli ingest"]
  push["Push to main"]
  backfillWf["Backfill<br/>workflow"]
  build["build<br/>cli export, astro build"]
  deploy["deploy<br/>GitHub Pages"]
  alerts["alerts<br/>cli alerts"]
  dispatch --> ingest
  cron --> ingest
  manual -->|"ingest"| ingest
  ingest -->|"commit to data"| build
  manual -->|"skip ingest"| build
  push --> build
  backfillWf --> build
  build --> deploy
  deploy -->|"after an ingest only"| alerts
```

### The weekly run

Steve's email arrives Friday around 5:20pm Pacific. Between 6 and 7pm the Drive publisher
(`scripts/drive-publisher.gs`, on a daily trigger) moves the new edition into the public Drive folder, points
`latest.json` at it, and dispatches the Deploy workflow. The cron runs later as a fallback: in a normal week it
finds the edition already ingested, redeploys, and sends no one a second Alert.

```mermaid
sequenceDiagram
  accTitle: The weekly run
  accDescr: The Drive publisher updates latest.json and dispatches Deploy. The ingest job reads the edition from Drive, looks new Venues and Bands up on the services and commits to the data branch. The build and deploy jobs publish the site to Pages. The alerts job reads Saved Filters from Supabase and sends each person's Alert through Resend.
  participant Drive
  participant GH as Deploy
  participant Svc as Services
  participant Data as data
  participant Pages
  participant SB as Supabase
  Note over Drive: publisher updates<br/>latest.json
  Drive->>GH: dispatch
  Note over GH: ingest job
  Drive->>GH: edition JSON
  GH->>Svc: new Venues,<br/>new Bands
  Svc->>GH: genres, links,<br/>photos
  GH->>Data: commit
  Note over GH: build, deploy
  Data->>GH: the data
  GH->>Pages: the site
  Note over GH: alerts job
  SB->>GH: Saved Filters
  GH->>SB: Alerts, via Resend
```

The services are Google Places (new Venues), and MusicBrainz, Last.fm, Discogs, Wikimedia Commons and Bandcamp
(new Bands). [How ingestion works](ingestion.md) has the ingest step by step, with what comes from each. The
Backfill workflow looks Bands ingested before a lookup existed up on the same services
(see [Deployment](deployment.md)).
