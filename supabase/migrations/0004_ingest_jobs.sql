-- Ingest jobs: Shows an admin asks for on the Admin page (/admin/), one per TicketWeb link or event screenshot
-- (see docs/adr/0006-admin-ingest-jobs.md).
--
--   Admin page --POST /functions/v1/admin/v1/shows--> enqueue_ingest_job(): a row in ingest_jobs + a message on the
--   ingest_jobs queue --> pg_cron, each minute: kick_ingest_worker() calls the ingest-worker Edge Function -->
--   claim_ingest_jobs() --> the Ingest jobs GitHub workflow, which ingests, deploys, and updates each job's row.
--
-- Apply by hand in the Supabase SQL editor, after 0003. First, in the dashboard: Integrations > Queues (pgmq),
-- Cron (pg_cron) and Database > Extensions > pg_net enabled. Then the two Vault secrets the cron reads:
--
--   select vault.create_secret('https://<project>.supabase.co/functions/v1/ingest-worker', 'ingest_worker_url');
--   select vault.create_secret('<the WORKER_SECRET given to the ingest-worker function>', 'ingest_worker_secret');
--
-- Make someone an admin (they sign out and in again for it to take effect: it rides in their session's token):
--
--   update auth.users set raw_app_meta_data = raw_app_meta_data || '{"permissions": ["admin"]}'
--   where email = 'someone@example.com';

create extension if not exists pgmq;
create extension if not exists pg_net;
create extension if not exists pg_cron;

-- ── Who's an admin ───────────────────────────────────────────────────────────

-- A person's permissions are in their app_metadata (auth.users.raw_app_meta_data), which only the project's
-- secret key or the SQL editor can change, and which their session's token carries.
create function public.is_admin() returns boolean
  language sql stable set search_path = '' as $$
  select coalesce((auth.jwt() -> 'app_metadata' -> 'permissions') ? 'admin', false);
$$;

grant execute on function public.is_admin() to authenticated;

-- ── The jobs ─────────────────────────────────────────────────────────────────

-- One Show to add. `status` is where it stands (queued, running: being ingested; added: in the data, not yet on
-- the site; live: deployed; failed, with `message`); `phase` is the step it's on, or failed at, and `detail` says
-- more ("Looking up Band 2 of 3: Wet Leg"). Phases, in order: queued, dispatched, fetching_page or
-- reading_screenshot, venue, bands, photos, saving, embedding, committing, deploying, live.
create table public.ingest_jobs (
  id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('ticketweb', 'screenshot')),
  url text check (char_length(url) <= 2000),
  screenshot_path text,
  status text not null default 'queued' check (status in ('queued', 'running', 'added', 'live', 'failed')),
  phase text not null default 'queued',
  detail text,
  message text,
  extracted jsonb,          -- what the vision model read from a screenshot
  show_id integer,          -- the Show, in the site's data: its page is /shows/<show_id>/
  workflow_run_url text,
  attempts integer not null default 0,
  created_by uuid default auth.uid() references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((provider = 'ticketweb') = (url is not null)),
  check ((provider = 'screenshot') = (screenshot_path is not null))
);

create index ingest_jobs_created_at_idx on public.ingest_jobs (created_at desc);

create function public.touch_ingest_job() returns trigger
  language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger ingest_jobs_touch before update on public.ingest_jobs
  for each row execute function public.touch_ingest_job();

alter table public.ingest_jobs enable row level security;

-- Admins read every job. Nobody writes them through the Data API but the workflow, with the secret key
-- (service_role); new jobs go through enqueue_ingest_job.
create policy "Ingest jobs: admins read them" on public.ingest_jobs
  for select to authenticated using ((select public.is_admin()));

grant select on public.ingest_jobs to authenticated;
grant select, update on public.ingest_jobs to service_role;

-- The Admin page follows its jobs as they change (Realtime respects the policy above).
alter publication supabase_realtime add table public.ingest_jobs;

-- ── The queue ────────────────────────────────────────────────────────────────

-- Each message is {"job_id": ...}. A message the workflow doesn't finish (the run was cancelled or crashed)
-- shows again once its visibility timeout runs out, and its job is handed out again (claim_ingest_jobs).
select pgmq.create('ingest_jobs');

-- ── Screenshots ──────────────────────────────────────────────────────────────

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('ingest-screenshots', 'ingest-screenshots', false, 10485760, array['image/png', 'image/jpeg', 'image/webp']);

create policy "Ingest screenshots: admins add them" on storage.objects
  for insert to authenticated with check (bucket_id = 'ingest-screenshots' and (select public.is_admin()));
create policy "Ingest screenshots: admins see them" on storage.objects
  for select to authenticated using (bucket_id = 'ingest-screenshots' and (select public.is_admin()));

-- ── Adding a job (the admin Edge Function, as the signed-in admin) ───────────

-- A job for a TicketWeb link (`url`) or an uploaded screenshot (`screenshot_path`), queued. A link that already
-- has a job in progress isn't queued twice: that job is returned instead.
create function public.enqueue_ingest_job(provider text, url text default null, screenshot_path text default null)
  returns public.ingest_jobs
  language plpgsql security definer set search_path = '' as $$
declare
  job public.ingest_jobs;
begin
  if not public.is_admin() then
    raise exception 'Only admins can add Shows' using errcode = '42501';
  end if;
  if url is not null then
    select * into job from public.ingest_jobs j
    where j.url = enqueue_ingest_job.url and j.status in ('queued', 'running');
    if found then
      return job;
    end if;
  end if;
  insert into public.ingest_jobs (provider, url, screenshot_path)
  values (enqueue_ingest_job.provider, enqueue_ingest_job.url, enqueue_ingest_job.screenshot_path)
  returning * into job;
  perform pgmq.send('ingest_jobs', jsonb_build_object('job_id', job.id));
  return job;
end;
$$;

revoke execute on function public.enqueue_ingest_job(text, text, text) from public, anon;
grant execute on function public.enqueue_ingest_job(text, text, text) to authenticated;

-- ── Handing jobs out (the ingest-worker Edge Function, with the secret key) ──

-- Up to `qty` queued jobs to run, each hidden on the queue for `vt` seconds. A job that has been handed out
-- `max_attempts` times already is failed and taken off the queue instead; one that has finished is just taken
-- off. Returns the jobs to dispatch, with their message ids.
create function public.claim_ingest_jobs(qty integer default 20, vt integer default 3600, max_attempts integer default 3)
  returns table (job_id uuid, msg_id bigint)
  language plpgsql security definer set search_path = '' as $$
declare
  m record;
  job public.ingest_jobs;
begin
  for m in select * from pgmq.read('ingest_jobs', vt, qty) loop
    select * into job from public.ingest_jobs where id = (m.message ->> 'job_id')::uuid;
    if not found or job.status in ('added', 'live') then
      perform pgmq.delete('ingest_jobs', m.msg_id);
    elsif job.attempts >= max_attempts then
      update public.ingest_jobs
      set status = 'failed', message = coalesce(message || ' ', '') || '(gave up after ' || job.attempts || ' attempts)'
      where id = job.id;
      perform pgmq.delete('ingest_jobs', m.msg_id);
    else
      update public.ingest_jobs
      set status = 'queued', phase = 'dispatched', detail = 'attempt ' || (attempts + 1), message = null,
          attempts = attempts + 1
      where id = job.id;
      job_id := job.id;
      msg_id := m.msg_id;
      return next;
    end if;
  end loop;
end;
$$;

revoke execute on function public.claim_ingest_jobs(integer, integer, integer) from public, anon, authenticated;
grant execute on function public.claim_ingest_jobs(integer, integer, integer) to service_role;

-- Claimed jobs whose workflow couldn't be started: shown again on the queue in `delay` seconds, the attempt not
-- counted.
create function public.release_ingest_jobs(msg_ids bigint[], delay integer default 300) returns void
  language plpgsql security definer set search_path = '' as $$
declare
  m record;
begin
  for m in select * from pgmq.set_vt('ingest_jobs', msg_ids, delay) loop
    update public.ingest_jobs set attempts = greatest(attempts - 1, 0) where id = (m.message ->> 'job_id')::uuid;
  end loop;
end;
$$;

revoke execute on function public.release_ingest_jobs(bigint[], integer) from public, anon, authenticated;
grant execute on function public.release_ingest_jobs(bigint[], integer) to service_role;

-- ── Finishing a job (the workflow, with the secret key) ──────────────────────

-- How the job's ingest came out, recorded and taken off the queue together.
create function public.finish_ingest_job(job_id uuid, msg_id bigint, new_status text, new_message text default null,
                                         new_show_id integer default null, new_extracted jsonb default null)
  returns void
  language plpgsql security definer set search_path = '' as $$
begin
  update public.ingest_jobs
  set status = new_status, message = new_message, show_id = coalesce(new_show_id, show_id),
      extracted = coalesce(new_extracted, extracted)
  where id = job_id;
  perform pgmq.delete('ingest_jobs', msg_id);
end;
$$;

revoke execute on function public.finish_ingest_job(uuid, bigint, text, text, integer, jsonb)
  from public, anon, authenticated;
grant execute on function public.finish_ingest_job(uuid, bigint, text, text, integer, jsonb) to service_role;

-- ── The worker's clock ───────────────────────────────────────────────────────

-- Each minute, when the queue has a message to hand out, call the ingest-worker Edge Function. Its URL and the
-- secret it checks are in Vault (see the top of this file).
create function public.kick_ingest_worker() returns void
  language plpgsql security definer set search_path = '' as $$
begin
  if exists (select 1 from pgmq.q_ingest_jobs where vt <= now()) then
    perform net.http_post(
      url := (select decrypted_secret from vault.decrypted_secrets where name = 'ingest_worker_url'),
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'x-worker-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'ingest_worker_secret')),
      body := '{}'::jsonb);
  end if;
end;
$$;

revoke execute on function public.kick_ingest_worker() from public, anon, authenticated;

select cron.schedule('ingest-worker', '* * * * *', 'select public.kick_ingest_worker()');
