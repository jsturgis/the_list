---
title: Deployment
description: The weekly Deploy workflow, the data branch, backfills and rollbacks.
order: 6
---

The site is published at **https://list.sturgis.me/** as a static site on GitHub Pages (see
[ADR 0002](https://github.com/jsturgis/the_list/blob/main/docs/adr/0002-static-site-on-github-pages.md)). The old address, https://jsturgis.github.io/the_list/,
redirects there.

- **Custom domain**: set in Settings → Pages, with a `CNAME` record `list` → `jsturgis.github.io` in the
  `sturgis.me` DNS. The build takes its base path and site URL from `actions/configure-pages`
  (`PAGES_BASE_PATH`, `PAGES_SITE_URL`): `""` and `https://list.sturgis.me` with the domain, `/the_list` and
  `https://jsturgis.github.io/the_list` without it. Local builds default to `/the_list`.

- **The `data` branch** is an orphan branch holding the SQLite database (`the_list.db`), the FAISS
  index (`faiss/`) and Band photos (`images/`). `main` never contains data files. It keeps only its newest 4 commits (the current
  data plus 3 to roll back to): after each ingest, older history is squashed into the oldest kept
  commit and the branch is force-pushed (`.github/scripts/prune-history.sh`).
- **The Deploy workflow** (`.github/workflows/deploy.yml`) has three stages (diagrams of its triggers and of the
  weekly run are in [Architecture](architecture.md#offline-jobs)):
  1. **Ingest**: runs `python -m app.cli ingest` against the `data` branch's database (with an Ollama
     service container for embeddings) and commits the changed database, index and Band photos back to
     `data`. Each run's row in `ingestion_runs` records its new Bands and, as percentages, how many have no
     photo and how many fell back to the edition for genres, photo and links (`app/ingestion/ingest_stats.py`;
     also in the `ingestionRuns` GraphQL query and the ingest log), to follow the lookups' coverage.
  2. **Build and deploy**: checks out `main` and the `data` branch, runs `python -m app.cli export`,
     copies `images/` into the site's static files, builds the static site and deploys it to Pages.
  3. **Alerts**: after a successful ingest and deploy only, runs `python -m app.cli alerts`. That emails
     each person whose Saved Filters match Upcoming Shows (see [Weekly Alerts](alerts.md)). It never
     runs on deploy-only runs. If it fails, the site stays deployed and the run shows red.
- **When it runs**:
  - **The Drive publisher's dispatch, first**: when it updates `latest.json` with a new edition (between
    6 and 7pm Pacific Friday), it starts this workflow itself (`workflow_dispatch`, ingestion on) through
    GitHub's API. Ingest, then deploy. See the script's header comment and
    [Drive setup](configuration.md#drive-setup).
  - **The Friday-night cron, as a fallback**: `37 6 * * 6` (Saturday 06:37 UTC = Friday 11:37pm PDT /
    10:37pm PST), late enough that a dispatched run has normally already finished. In a normal week this
    finds the edition already ingested and just redeploys, sending no one a second Alerts email (same
    Pacific day, so it reuses the dispatch run's idempotency key); in a week the dispatch didn't fire, it
    ingests, deploys and sends Alerts the way the scheduled run always has.
  - **By hand** from the Actions tab (**Deploy → Run workflow**) or `gh workflow run deploy.yml`.
    A manual run with ingest also sends Alerts (re-running the same day sends no one a second email).
    Tick **Skip ingestion** (`gh workflow run deploy.yml -f skip_ingest=true`) to rebuild from the
    existing data without sending Alerts.
  - **On pushes to `main`** that touch `frontend/` or `backend/app/`: deploy only, no ingest.
  - Only one run at a time.
- **A week with no new edition** still succeeds and redeploys (the run is recorded as `no_email`).
- **A failed ingest** fails the run: the `data` branch is left untouched and nothing is deployed.
  GitHub emails you about failed scheduled runs (Settings → Notifications → Actions).
- **Settings**: Pages source must be **GitHub Actions** (Settings → Pages). The ingest uses the
  `GOOGLE_MAPS_API_KEY`, `LASTFM_API_KEY`, `DISCOGS_CONSUMER_KEY` and `DISCOGS_CONSUMER_SECRET` secrets and the
  `DRIVE_LATEST_FILE_ID` repository variable
  (Settings → Secrets and variables → Actions). No Anthropic key: ingestion makes no LLM calls.
- **The Backfill workflow** (`.github/workflows/backfill.yml`, run by hand: **Backfill → Run workflow** or
  `gh workflow run backfill.yml`) brings Bands ingested before a lookup existed up to what new Bands get:
  `python -m app.cli backfill` looks each one up on MusicBrainz, Last.fm, Discogs and Wikimedia Commons by the
  ingest's rules (`app/ingestion/band_sources.py`; what the Band already has is the last fallback), re-embeds it
  when its genres change, and stores its new photo. Each Band looked up gets `enriched_at`, so it's resumable:
  a run takes the Bands not yet looked up (those on Upcoming Shows first), stops after **max minutes** (default
  300, under the 6-hour job limit) or **limit** Bands, commits to `data` and starts a deploy-only Deploy. Run it
  again until its commit message says none are still to do. Discogs' rate limit (one request a second) sets
  the pace. It needs `LASTFM_API_KEY` and both Discogs keys and the genre model, and checks first that Last.fm and
  Discogs accept the keys and the model answers. Tick **recheck genres** (`--recheck-genres`) to first mark the
  Bands whose stored genres hold a tag that isn't a genre, so the run looks them up again. A service that's
  down mid-run returns nothing, and those Bands are still marked looked up. Locally (with the keys in `backend/.env`):
  `docker compose exec api python -m app.cli backfill --limit 20`.
- **Genres are filtered** (`app/ingestion/genre_filter.py`): Last.fm's tags and MusicBrainz's free-form tags keep
  only genres. A tag in MusicBrainz's genre list (`app/ingestion/genres.txt`) or a known shorthand is kept; any
  other is judged once by the `tev1:0.8b` decision model on Ollama, and the answer is stored in the `genre_tags`
  table. To overrule it, edit that row on the `data` branch (`is_genre`, and `decided_by = 'hand'`).
- **Photo focal points** (`app/ingestion/photo_focus.py`): each Band photo the ingest or backfill stores gets a
  focal point (`bands.image_focus`) from the faces in it, and the site crops the photo around it. Photos stored
  before focal points need one run of `python -m app.cli photo-focus`, which works them out from the files in
  `images/` (no network; it only looks at Bands without one, commits every 100, and can be run again; `--all`
  redoes every photo). To run it on the `data` branch, from a checkout of `main`:

  ```bash
  git fetch origin data
  git worktree add -B data ../the_list-data origin/data
  docker compose build api        # the image needs opencv-python-headless
  docker compose run --rm --no-deps -v "$PWD/../the_list-data:/data" \
    -e DATABASE_URL=sqlite:////data/the_list.db -e IMAGES_PATH=/data/images \
    api sh -c "alembic upgrade head && python -m app.cli photo-focus"
  cd ../the_list-data && git add the_list.db && git commit -m "Focal points for stored Band photos" && git push origin data
  gh workflow run deploy.yml -f skip_ingest=true
  ```
- **Updating the data by hand**: commit a new `the_list.db` and `faiss/` to the `data` branch, then run
  the workflow with **Skip ingestion**.
- **Rolling back**: revert the bad commit on the `data` branch (`git revert <sha>` on a checkout of
  `data`, then push) and run the workflow with **Skip ingestion**. Only the last 3 changes can be rolled
  back this way. The branch is rewritten when it's pruned, so fetch it fresh
  (`git fetch origin data && git reset --hard origin/data`) before committing to it by hand.
