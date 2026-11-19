-- Retry a job from the Admin page (docs/adr/0006-admin-ingest-jobs.md): one that failed, or that has stalled (no
-- progress for 30 minutes while queued or running). An added job isn't: it waits on its Deploy, which can take an
-- hour or more in the `pages` concurrency group, and ingesting it again wouldn't publish it.
--
-- A run that breaks off fails its unfinished jobs and the queue hands them out again within the hour, up to three
-- attempts; a run GitHub cancels while it waits in its concurrency group runs no step at all, so its jobs sit at
-- "Dispatched" until then; a Deploy that fails leaves a job failed for good. Retrying starts the job over at once:
-- attempts back to 0, its queue message shown now (or sent again, when it was taken off), so the worker dispatches
-- it within a minute. A reviewed job keeps its approved fields, and is added as approved. A stalled job's run may in
-- fact be waiting in the `pages` group (behind a Backfill) rather than cancelled; retrying it starts a new run,
-- GitHub cancels the waiting one, and that run's other jobs are handed out again when their messages show (as they
-- would be had it been cancelled anyway). Runs never overlap, and a run skips a job another already added, so
-- nothing is added twice.
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
  -- The message first, as claim_ingest_jobs takes it (pgmq.read locks messages, skipping locked ones), so the two
  -- never wait on each other's locks.
  select q.msg_id into msg from pgmq.q_ingest_jobs q where q.message ->> 'job_id' = retry_ingest_job.job_id::text
  order by q.msg_id limit 1 for update;
  update public.ingest_jobs j
  set status = 'queued', phase = 'queued', detail = null, message = null, attempts = 0, workflow_run_url = null
  where j.id = retry_ingest_job.job_id
    and (j.status = 'failed'
         or (j.status in ('queued', 'running') and j.updated_at < now() - interval '30 minutes'))
  returning * into job;
  if not found then
    raise exception 'That job can''t be retried: it hasn''t failed or stalled' using errcode = 'P0002';
  end if;
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
