-- A link to a page listing several events (an artist's page) adds a Show for each in the Bay Area. The job's
-- `show_id` is the first; `shows_query` is the Shows list's filter that picks them all out
-- ("bandId=12&fromDate=2027-01-21&toDate=2027-01-24", frontend/src/lib/filters.ts), which the Admin page links to.
-- Null for a job that added one Show. Set by the Ingest jobs workflow (backend/app/ingest_jobs.py, shows_query).
--
-- Apply by hand in the Supabase SQL editor, after 0007, before the backend that sends it is merged (it only sends
-- it for a job that added several Shows).

alter table public.ingest_jobs
  add column shows_query text check (char_length(shows_query) <= 200);

-- finish_ingest_job, as in 0004, also setting shows_query. Dropped and made again: a new parameter would otherwise
-- make a second function beside the old one.
drop function public.finish_ingest_job(uuid, bigint, text, text, integer, jsonb);

create function public.finish_ingest_job(job_id uuid, msg_id bigint, new_status text, new_message text default null,
                                         new_show_id integer default null, new_extracted jsonb default null,
                                         new_shows_query text default null)
  returns void
  language plpgsql security definer set search_path = '' as $$
begin
  update public.ingest_jobs
  set status = new_status, message = new_message, show_id = coalesce(new_show_id, show_id),
      extracted = coalesce(new_extracted, extracted), shows_query = coalesce(new_shows_query, shows_query)
  where id = job_id;
  perform pgmq.delete('ingest_jobs', msg_id);
end;
$$;

revoke execute on function public.finish_ingest_job(uuid, bigint, text, text, integer, jsonb, text)
  from public, anon, authenticated;
grant execute on function public.finish_ingest_job(uuid, bigint, text, text, integer, jsonb, text) to service_role;
