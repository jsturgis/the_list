-- Admins clear finished ingest jobs from the Admin page (its trash can), and a screenshot job's screenshot with it.
-- Only finished jobs (failed, or live on the site): one still on its way would leave its queue message and its run
-- with nothing to report to.
--
-- Apply by hand in the Supabase SQL editor, after 0005.

create policy "Ingest jobs: admins delete finished ones" on public.ingest_jobs
  for delete to authenticated using ((select public.is_admin()) and status in ('failed', 'live'));

grant delete on public.ingest_jobs to authenticated;

create policy "Ingest screenshots: admins delete them" on storage.objects
  for delete to authenticated using (bucket_id = 'ingest-screenshots' and (select public.is_admin()));
