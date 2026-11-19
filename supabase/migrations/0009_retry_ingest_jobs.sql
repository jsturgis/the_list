-- Retry a job from the Admin page (docs/adr/0006-admin-ingest-jobs.md): one that failed, or that has stalled (no
-- progress for 30 minutes while queued, running or added). A run that breaks off fails its unfinished jobs and the
-- queue hands them out again within the hour, up to three attempts; a run GitHub cancels while it waits in its
-- concurrency group runs no step at all, so its jobs sit at "Dispatched" until then; a Deploy that fails leaves a job
-- failed for good. Retrying starts the job over at once: attempts back to 0, its queue message shown now (or sent
-- again, when it was taken off), so the worker dispatches it within a minute. A reviewed job keeps its approved
-- fields, and is added as approved. Adding a Show again only updates it, so a job retried while it was in fact still
-- going adds nothing twice.
--
-- Apply by hand in the Supabase SQL editor, after 0008, before the Admin page that calls it is deployed.

create function public.retry_ingest_job(job_id uuid) returns public.ingest_jobs
  language plpgsql security definer set search_path = '' as $$
declare
  job public.ingest_jobs;
  msg bigint;
begin
  if not public.is_admin() then
    raise exception 'Only admins can retry jobs' using errcode = '42501';
  end if;
  update public.ingest_jobs j
  set status = 'queued', phase = 'queued', detail = null, message = null, attempts = 0, workflow_run_url = null
  where j.id = retry_ingest_job.job_id
    and (j.status = 'failed'
         or (j.status in ('queued', 'running', 'added') and j.updated_at < now() - interval '30 minutes'))
  returning * into job;
  if not found then
    raise exception 'That job can''t be retried: it hasn''t failed or stalled' using errcode = 'P0002';
  end if;
  select q.msg_id into msg from pgmq.q_ingest_jobs q where q.message ->> 'job_id' = job.id::text
  order by q.msg_id limit 1;
  if msg is not null then
    perform pgmq.set_vt('ingest_jobs', msg, 0);
  else
    perform pgmq.send('ingest_jobs', jsonb_build_object('job_id', job.id));
  end if;
  return job;
end;
$$;

revoke execute on function public.retry_ingest_job(uuid) from public, anon;
grant execute on function public.retry_ingest_job(uuid) to authenticated;
