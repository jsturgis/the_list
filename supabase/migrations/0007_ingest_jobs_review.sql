-- A screenshot job waits for review once its screenshot is read (see docs/adr/0006-admin-ingest-jobs.md): status
-- 'review', with what the vision model read in `extracted`. Nothing is added until an admin approves it, corrected
-- as need be (approve_ingest_job): the next run adds it as approved, without asking the model again. Discarding it
-- is deleting it.
--
-- Apply by hand in the Supabase SQL editor, after 0006.

alter table public.ingest_jobs
  drop constraint ingest_jobs_status_check,
  add constraint ingest_jobs_status_check check (status in ('queued', 'running', 'review', 'added', 'live', 'failed')),
  add column approved_at timestamptz,
  add column approved_by uuid references auth.users (id) on delete set null;

-- Approve a screenshot job waiting for review, with its fields as the admin left them (the same shape the model
-- answers in: backend/app/ingestion/screenshot.py), and queue it to be added.
create function public.approve_ingest_job(job_id uuid, fields jsonb) returns public.ingest_jobs
  language plpgsql security definer set search_path = '' as $$
declare
  job public.ingest_jobs;
begin
  if not public.is_admin() then
    raise exception 'Only admins can approve Shows' using errcode = '42501';
  end if;
  if jsonb_typeof(fields) is distinct from 'object' then
    raise exception 'The details to approve must be an object' using errcode = '22023';
  end if;
  update public.ingest_jobs
  set extracted = fields, approved_at = now(), approved_by = auth.uid(), status = 'queued', phase = 'queued',
      detail = null, message = null, attempts = 0
  where id = job_id and status = 'review'
  returning * into job;
  if not found then
    raise exception 'That job isn''t waiting for review' using errcode = 'P0002';
  end if;
  perform pgmq.send('ingest_jobs', jsonb_build_object('job_id', job.id));
  return job;
end;
$$;

revoke execute on function public.approve_ingest_job(uuid, jsonb) from public, anon;
grant execute on function public.approve_ingest_job(uuid, jsonb) to authenticated;

-- Discarding a job waiting for review deletes it, as a finished one is (0006).
drop policy if exists "Ingest jobs: admins delete finished ones" on public.ingest_jobs;
create policy "Ingest jobs: admins delete finished ones" on public.ingest_jobs
  for delete to authenticated using ((select public.is_admin()) and status in ('failed', 'live', 'review'));
