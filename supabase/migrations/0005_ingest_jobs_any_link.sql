-- Ingest jobs take a link to any site's event page, not only TicketWeb's (see docs/adr/0006-admin-ingest-jobs.md):
-- `provider` 'page' is any other site, read from the schema.org Event it describes itself with
-- (backend/app/ingestion/event_page.py). A job has a link unless it's a screenshot.
--
-- Apply by hand in the Supabase SQL editor, after 0004.

alter table public.ingest_jobs
  drop constraint ingest_jobs_provider_check,
  drop constraint ingest_jobs_check,
  add constraint ingest_jobs_provider_check check (provider in ('ticketweb', 'page', 'screenshot')),
  add constraint ingest_jobs_check check ((provider = 'screenshot') = (url is null));
