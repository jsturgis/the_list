# Adding Shows from the Admin page: ingest jobs on Supabase, run by GitHub Actions

Shows the List doesn't have yet were added by running `scripts/add-event.sh` on a laptop. The Admin page (`/admin/`) lets an admin do it from the site: they paste links to events' pages on any site, or drop in screenshots of events, and each becomes an **ingest job** that ends with the Show on the site. The site is static with no server of its own (ADR 0002), so the parts that need one run on **Supabase**, which already holds accounts (ADR 0003). The ingest itself runs where it always has, in **GitHub Actions** against the `data` branch.

```
Admin page ──POST /functions/v1/admin/v1/shows──▶ admin Edge Function ──▶ ingest_jobs row + message on the ingest_jobs queue
pg_cron, each minute ──▶ ingest-worker Edge Function ──claim_ingest_jobs──▶ GitHub: Ingest jobs workflow (jobs=id:msg,...)
Ingest jobs workflow ──▶ python -m app.cli ingest-jobs ──▶ commit data ──▶ Deploy ──▶ each job's row: status, phase, detail
Admin page ◀── Realtime (or polling) on ingest_jobs
```

This amends ADR 0003: Supabase now also holds the jobs, their queue, the screenshots and the worker. Show data still lives only in the `data` branch and the static export.

## Decisions

- **The database is the record, the queue hands out work.** A job's row in `ingest_jobs` says where it stands: `status` (queued, running, added, live, failed) and `phase` (queued, dispatched, fetching_page or reading_screenshot, venue, bands, photos, saving, embedding, committing, deploying, live), with a `detail` ("Looking up Band 2 of 3: Wet Leg"). Its message on the pgmq queue `ingest_jobs` is what gets it run.
- **The queue's visibility timeout is the retry.** The worker reads messages for an hour (`claim_ingest_jobs`). `finish_ingest_job` records a job's outcome and deletes its message in one transaction. A run that never finishes a job leaves its message, which shows again and is handed out again, up to three attempts. Runs can be cancelled because the workflow's ingest job shares the `pages` concurrency group with Deploy and Backfill, so it never writes `data` alongside them, and GitHub keeps only one waiting run per group.
- **Admins are named in `app_metadata`**, as `"permissions": ["admin"]`. Supabase manages `auth.users` and doesn't support adding columns to it. `raw_app_meta_data` is its column for this: only the secret key or the SQL editor can change it, and it rides in the session token. So `public.is_admin()` reads it there for row-level security, the Edge Function reads it from the verified user, and the page reads it to decide what to show.
- **Everything an admin does goes through the database as the admin.** The admin Edge Function calls `enqueue_ingest_job` and uploads screenshots with the caller's token, so the policies apply to it. Only the worker and the workflow use the secret key.
- **Any site's link; a screenshot when its page can't be read.** A link to TicketWeb is read by its own reader; any other site's page is read from the schema.org Event it describes itself with (`app/ingestion/event_page.py`, `provider` 'page'). Many sites turn scripted requests away, and TicketWeb itself answers GitHub's runners with Cloudflare's 530, so a link whose page can't be fetched or has no event details fails with a request for a screenshot, and the Admin page offers one ("Add a screenshot instead"). A link to an event that can't be added at all (outside the Bay Area, past) just fails.
- **Bandsintown is read from screenshots.** Bandsintown answers scripted requests with Cloudflare's block page, and its API needs a partner app_id. An admin adds a screenshot of the event instead, from Bandsintown or anywhere else. A vision model on Ollama (`qwen2.5vl:3b`, `settings.vision_model`) reads it into the fields of an event. A screenshot over 1.6 million pixels (a full-screen Retina one is 7.7 million) is scaled down first, and the model's context set to 8,192 tokens: it sees an image as a token per 28×28 pixels, and its default context of 4,096 can't hold a large one (Ollama answers 400), and `app/ingestion/screenshot.py` checks them as an event page's are: a lineup, a Bay Area Venue, a date that hasn't passed. What it read is kept on the job (`extracted`), so a misreading can be seen.
- **The Deploy is seen through.** The workflow's `publish` job runs outside the `pages` group, so the Deploy it starts can run. It follows that Deploy (`.github/scripts/await-deploy.sh`) and marks the jobs `live`. It follows a waiting *manual* Deploy rather than starting one, but not a waiting scheduled one: a scheduled Deploy stops after its check when the List hasn't changed, and never rebuilds the site.

## Considered options

- **A hosted API (FastAPI on Fly or Render) with a worker process**: matches a textbook design, but means a server to run and pay for. ADR 0002 chose not to have one.
- **Dispatching the workflow straight from the admin function**: simpler, but a run cancelled in the `pages` group would strand its jobs with nothing to retry them.
- **pg_net calling GitHub from a trigger**: no worker function, but the GitHub token would live in Vault and dispatch failures would be invisible.

## Consequences

- **Setup, once:**
  1. In the dashboard, enable Queues (pgmq), Cron (pg_cron) and pg_net.
  2. Apply `supabase/migrations/0004_ingest_jobs.sql` in the SQL editor.
  3. Deploy the functions: `supabase functions deploy admin` and `supabase functions deploy ingest-worker --no-verify-jwt`.
  4. Set the function secrets: `supabase secrets set WORKER_SECRET=… GITHUB_TOKEN=… GITHUB_REPO=jsturgis/the_list`. `GITHUB_TOKEN` is a fine-grained token with Actions: read and write on this repository only.
  5. Store the worker's URL and the same secret in Vault, as `ingest_worker_url` and `ingest_worker_secret` (see the migration's header).
  6. Add `https://list.sturgis.me/admin/**` to Auth's redirect allow-list.
  7. Make yourself an admin (see the migration's header), then sign out and in again.
- The Ingest jobs workflow uses the secrets Deploy already has. Its Ollama cache now also holds the vision model, about 3 GB.
- Starting a Deploy, or a waiting Ingest jobs run, replaces a Deploy already waiting in the `pages` group, so an hourly check can be skipped. The next hour's check runs as usual.
- A job is retried only when its run broke off. A job that failed on its own (a page that can't be read, a city outside the Bay Area) stays failed. Add it again once it's fixed.
- Screenshots stay in the private `ingest-screenshots` bucket. Nothing deletes them yet.
