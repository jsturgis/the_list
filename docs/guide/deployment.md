---
title: Deployment
description: The Deploy workflow and its hourly check, the data branch, backfills and rollbacks.
---

The site is published at **https://list.sturgis.me/** as a static site on GitHub Pages (see
[ADR 0002](https://github.com/jsturgis/the_list/blob/main/docs/adr/0002-static-site-on-github-pages.md)). The old address, https://jsturgis.github.io/the_list/,
redirects there. Diagrams of the Deploy workflow's triggers and of a new edition's run are in
[Architecture](architecture.md#offline-jobs).

## The `data` branch

An orphan branch holding the SQLite database (`the_list.db`), the FAISS index (`faiss/`) and Band photos
(`images/`). `main` never contains data files. It keeps only its newest 4 commits (the current data plus 3 to roll
back to): after each ingest, older history is squashed into the oldest kept commit and the branch is force-pushed
(`.github/scripts/prune-history.sh`). Each workflow that commits to it first runs SQLite's `integrity_check` and fails
rather than commit a damaged database. For anything older, the Back up the data workflow keeps nightly snapshots
(see [Rolling back](#rolling-back)).

## The Deploy workflow

`.github/workflows/deploy.yml` has five jobs, in four stages:

0. **Check** (the `check` job): runs `python -m app.cli check` against the `data` branch's database. It fetches
   Steve's page ([stevelist.com/list](https://stevelist.com/list)) and compares its SHA-256 with the page the last
   successful ingest read (`changed`), and the week (Friday to Thursday) of the date in its header with the newest edition
   ingested (`new_edition`). On the hourly cron, an unchanged page ends the run here.
1. **Ingest** (the `ingest` job): runs `python -m app.cli ingest` against the `data` branch's database (with an
   Ollama service container for embeddings) and commits the changed database, index and Band photos back to
   `data`. Each run's row in `ingestion_runs` records the edition's date, the page's hash, its new Venues, its new Bands and, as a
   percentage, how many of them have no photo (`app/ingestion/ingest_stats.py`;
   also in the `ingestionRuns` GraphQL query and the ingest log), to follow the lookups' coverage.
2. **Build and deploy** (the `build` and `deploy` jobs): checks out `main` and the `data` branch, runs
   `python -m app.cli export`, copies `images/` into the site's static files, builds the static site and deploys
   it to Pages. The site's `deployed.json` says what it was built from (`.github/scripts/site-inputs.sh`: the
   `data` branch's tree and the trees of `main` the build reads). Each hourly check compares it with the live
   site's, so a deploy that failed or was cancelled is redone at the next hourly run, even without an ingest.
3. **Alerts** (the `alerts` job): after the successful ingest and deploy of a new edition, runs
   `python -m app.cli alerts`. That emails each person whose Saved Filters match Upcoming Shows (see
   [Weekly Alerts](alerts.md)), and records that they went out (`alerts_sent_at` on the edition's run, committed to
   `data`). It never runs for a correction to the current edition, or on a push or **Skip ingestion** run. If it
   fails (the deploy or a send failed), the site stays deployed and the run shows red; each hourly check then finds
   the edition still due its Alerts (`alerts_due`) and sends them once the live site is up to date, until the
   edition's week ends.

Only one run at a time: a newer run waits for the one in progress.

- **An unchanged List** costs one short `check` job an hour: no ingest, no deploy, no row in `ingestion_runs`.
- **A page that can't be fetched, or isn't the List** (no edition date, or fewer than 20 listings) fails the run;
  the next hour's check tries again.
- **A failed ingest** fails the run: the `data` branch is left untouched and nothing is deployed. The page still
  counts as changed, so the next hour's run tries it again.
  GitHub emails you about failed scheduled runs (Settings → Notifications → Actions).

## The maintainer's emails

Besides GitHub's own emails about failed runs, the workflow emails the maintainer (`MAINTAINER_EMAIL`) about the
ingest, through Resend from `ALERTS_FROM` (`app/notifications.py`). These aren't Alerts: they go to the maintainer
only, and say how the ingest went.

- **After each successful ingest**: "The List: ingest succeeded: 12 new bands, 2 new venues", with the edition,
  its Shows parsed, upserted and new, the share of new Bands without a photo, and a link to the site. The
  `ingest` job sends it (`python -m app.cli notify-success`) once the data is committed to the `data` branch, from
  the committed database, so it never reports data that wasn't saved. An ingest that brought no new Shows sends
  nothing.
- **While the ingest has been failing for two weeks**: "The List: ingest failing for 15 days: ListError: …", with
  the root cause (the final exception, one line), which job failed (`check` or `ingest`), when the last successful
  ingest was and its edition, the last 60 lines of the failing job's log, and a link to the Actions run. A step
  with `if: failure()` at the end of the `check` and `ingest` jobs sends it (`python -m app.cli notify-failure
  --stage check|ingest --log PATH`); the jobs' commands also write their output to that log.

  A failed ingest isn't committed to the `data` branch (the job stops before the commit), and a failed check
  records nothing, so the database can't count failures. "Failing for two weeks" is: this attempt just failed,
  and the newest successful ingest finished 14 days ago or more (`FAILING_AFTER_DAYS`). A List that hasn't
  changed for two weeks isn't a failure: its checks succeed and nothing is sent. A database with no successful
  ingest sends nothing. The root cause of a failed ingest comes from its run's traceback, in the job's own copy of
  the database; otherwise from the log.

  The cron is hourly, so a lasting failure would email every hour: the email goes **at most once a day** (the Bay
  Area's day). Its Resend `Idempotency-Key` is the recipient and the date, and Resend refuses the day's later,
  different emails with that key. The root cause and the log are sent with credentials taken out (query-string
  `api_key=`, `key=`, `token=`, `secret=`, Authorization and Bearer values, and every key in the settings).

Without `MAINTAINER_EMAIL` or `RESEND_API_KEY` both commands log that they're skipping and exit 0. A failed send
fails only its own step, which has `continue-on-error`, so it can't change the ingest's result. Both commands take
`--dry-run`, which prints the email instead (`notify-failure --dry-run` prints it whether or not it's due).

## When it runs

- **Every hour**, at 17 minutes past (`17 * * * *`): check, and only when Steve's page has changed, ingest and
  deploy. Steve posts each Friday's edition ahead of it (the November 13, 2026 edition went up the Thursday night),
  so a new edition's Alerts go out within about an hour of his posting it, at whatever hour that is.
  GitHub disables a public repository's scheduled workflows after 60 days without activity, so each hourly run
  first re-enables the workflow through GitHub's API (the "Keep the hourly schedule enabled" step). GitHub doesn't
  document that this resets the 60 days. If the schedule ever stops anyway, the Actions tab shows the workflow as
  disabled: click **Enable workflow**, or run `gh workflow enable deploy.yml`. No failure email can warn you of
  this, as no run happens.
  GitHub's own cron is unreliable (it delays and drops runs), so a Google Cloud Scheduler job also dispatches the
  workflow every hour, with no inputs. A dispatch without inputs is the same hourly check: an unchanged List ends
  it after the check job.
- **By hand** from the Actions tab (**Deploy → Run workflow**) or `gh workflow run deploy.yml`: the hourly check,
  run now. Tick **Ingest even if the List hasn't changed** (`gh workflow run deploy.yml -f force_ingest=true`) to
  ingest it anyway (Alerts still go only for a new edition), or **Skip ingestion**
  (`gh workflow run deploy.yml -f skip_ingest=true`) to rebuild from the existing data without sending Alerts.
- **On pushes to `main`** that touch `frontend/`, `backend/app/`, `docs/guide/` (these docs) or the workflow's
  own file: deploy only, no ingest.
- **After the Backfill workflow**, which starts a deploy-only run when it has committed to `data`.

## Settings

- **Pages**: the source must be **GitHub Actions** (Settings → Pages).
- **Custom domain**: set in Settings → Pages, with a `CNAME` record `list` → `jsturgis.github.io` in the
  `sturgis.me` DNS. The build takes its base path and site URL from `actions/configure-pages`
  (`PAGES_BASE_PATH`, `PAGES_SITE_URL`): `""` and `https://list.sturgis.me` with the domain, `/the_list` and
  `https://jsturgis.github.io/the_list` without it. Local builds default to `/the_list`.
- **The ingest** uses the `GOOGLE_MAPS_API_KEY`, `ANTHROPIC_API_KEY`, `LASTFM_API_KEY`, `DISCOGS_CONSUMER_KEY` and
  `DISCOGS_CONSUMER_SECRET` secrets (Settings → Secrets and variables → Actions). Steve's page needs none. The
  Anthropic key is only for reading Venues' own calendars (flyers and more-info links); without it that step is
  skipped and nothing else changes.
- **Alerts** have their own secrets and variables: see [Weekly Alerts](alerts.md).
- **The maintainer's emails** need the `MAINTAINER_EMAIL` secret (where they go) and the Alerts' `RESEND_API_KEY`
  secret and `ALERTS_FROM` variable. Without `MAINTAINER_EMAIL` none are sent.

## The Backfill workflow

`.github/workflows/backfill.yml` brings Bands ingested before a lookup existed up to what new Bands get. Run it by
hand: **Backfill → Run workflow**, or `gh workflow run backfill.yml`.

- **What it does**: `python -m app.cli backfill` looks each Band up on MusicBrainz, Last.fm, Discogs, Wikimedia
  Commons and Bandcamp by the ingest's rules (`app/ingestion/band_sources.py`; what the Band already has is the last
  fallback), re-embeds it when its genres change, and stores its new photo.
- **It's resumable**: each Band looked up gets `enriched_at`. A run takes the Bands not yet looked up (those on
  Upcoming Shows first), stops after **max minutes** (default 300, under the 6-hour job limit) or **limit** Bands,
  commits to `data` and starts a deploy-only Deploy. Run it again until its commit message says none are still to
  do. Discogs' rate limit (one request a second) sets the pace.
- **What it needs**: `LASTFM_API_KEY`, both Discogs keys and the genre model. It checks first that Last.fm and
  Discogs accept the keys and the model answers.
- **A service that's down mid-run** (no answer, a timeout, a server error, a rate limit or a rejected key; not
  "no such artist") leaves the Band not looked up, with whatever the other services had, so the next run tries it
  again (`app/ingestion/service_health.py`). The same goes for a new Band at ingest, and each hourly ingest looks
  up again up to 10 Bands an earlier run left this way, so a short outage needs no Backfill run. Bandcamp is
  the same: a Band whose page Bandcamp won't serve stays pending for the next run.
- **Options that first mark Bands to look up again**:
  - **recheck genres** (`--recheck-genres`): Bands whose stored genres hold a tag that isn't a genre.
  - **recheck photos** (`--recheck-photos`): Bands with a Bandcamp page and no photo from a service.
  - **redo** (`--redo "<name>"`, names separated by `;` in the workflow): Bands matched to the wrong artist, looked
    up again from scratch. Use it after adding a Band's correction (see
    [How ingestion works](ingestion.md#fixing-data-by-hand)).
- **Locally** (with the keys in `backend/.env`): `docker compose exec api python -m app.cli backfill --limit 20`.

## Genres and photo focal points

- **Genres are filtered** (`app/ingestion/genre_filter.py`): Last.fm's tags and MusicBrainz's free-form tags keep
  only genres. A tag in MusicBrainz's genre list (`app/ingestion/genres.txt`) or a known shorthand is kept; any
  other is judged once by the `tev1:0.8b` decision model on Ollama, and the answer is stored in the `genre_tags`
  table. To overrule it, edit that row on the `data` branch (`is_genre`, and `decided_by = 'hand'`).
- **Photo focal points** (`app/ingestion/photo_focus.py`): each Band photo the ingest or backfill stores gets a
  focal point (`bands.image_focus`) from the faces in it, and the site crops the photo around it. Photos stored
  before focal points need one run of `python -m app.cli photo-focus`, which works them out from the files in
  `images/` (no network; it only looks at Bands without one, commits every 100, and can be run again; `--all`
  redoes every photo). The next section shows how to run it on the `data` branch.

## Changing the data by hand

To run a command against the published data, check the `data` branch out beside the repository and point the
backend at it. This example runs `photo-focus`, from a checkout of `main`:

```bash
git fetch origin data
git worktree add -B data ../the_list-data origin/data
docker compose build api        # the image needs the current code
docker compose run --rm --no-deps -v "$PWD/../the_list-data:/data" \
  -e DATABASE_URL=sqlite:////data/the_list.db -e IMAGES_PATH=/data/images -e FAISS_INDEX_PATH=/data/faiss \
  api sh -c "alembic upgrade head && python -m app.cli photo-focus"
cd ../the_list-data && git add -A && git commit -m "Focal points for stored Band photos" && git push origin data
gh workflow run deploy.yml -f skip_ingest=true
```

The branch is rewritten when it's pruned, so if the worktree already exists, bring it up to date first with
`git fetch origin data && git reset --hard origin/data` (never `pull`). To replace the data outright, commit a new
`the_list.db` and `faiss/` to the branch, then run the workflow with **Skip ingestion**.

## Rolling back

Revert the bad commit on the `data` branch (`git revert <sha>` on an up-to-date checkout of `data`, then push) and
run the workflow with **Skip ingestion**. Only the last 3 changes can be rolled back this way.

Further back, use a nightly snapshot. `.github/workflows/backup-data.yml` runs at 11:43 UTC (or by hand: **Back up
the data → Run workflow**), checks the database and uploads the whole `data` branch as an artifact named
`data-<date>-<sha>`, kept for 90 days; the run fails if `integrity_check` finds damage. To restore one:

```bash
gh run list --workflow backup-data.yml          # pick the night before the damage
gh run download <run-id> -D /tmp/snapshot && tar -xzf /tmp/snapshot/*/data.tar.gz -C /tmp/snapshot
cd ../the_list-data && git fetch origin data && git reset --hard origin/data
cp /tmp/snapshot/the_list.db . && rsync -a --delete /tmp/snapshot/faiss/ faiss/ && rsync -a --delete /tmp/snapshot/images/ images/
git add -A the_list.db faiss images && git commit -m "Restore the data from the <date> snapshot" && git push origin data
gh workflow run deploy.yml -f skip_ingest=true
```

Shows ingested since the snapshot come back at the next hourly ingest of a changed List, or run the Deploy workflow
with **Ingest even if the List hasn't changed**.
