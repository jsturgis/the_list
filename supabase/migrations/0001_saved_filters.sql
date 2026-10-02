-- Saved Filters and Alert subscriptions (see docs/adr/0003-saved-filter-alerts-on-supabase.md).
--
-- Apply by hand in the Supabase SQL editor. The project was created with "Automatically expose new tables"
-- off and "Enable automatic RLS" on, so tables are reachable through the Data API only with the grants
-- below, and only for the rows the policies allow.

-- ── Saved Filters ────────────────────────────────────────────────────────────

-- A named set of Show filters: `query` is the Shows list's URL query string (e.g. "genre=punk&region=sf").
create table public.saved_filters (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 80),
  query text not null check (char_length(query) between 1 and 500),
  created_at timestamptz not null default now()
);

create index saved_filters_user_id_idx on public.saved_filters (user_id);

alter table public.saved_filters enable row level security;

create policy "Saved Filters: read your own" on public.saved_filters
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "Saved Filters: add your own" on public.saved_filters
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "Saved Filters: delete your own" on public.saved_filters
  for delete to authenticated using ((select auth.uid()) = user_id);

grant select, insert, delete on public.saved_filters to authenticated;

-- ── Alert subscriptions ──────────────────────────────────────────────────────

-- Whether a person gets the weekly Alert, and the token their unsubscribe link carries. Created with
-- their first Saved Filter (see the trigger below).
create table public.alert_subscriptions (
  user_id uuid primary key references auth.users (id) on delete cascade,
  enabled boolean not null default true,
  unsubscribe_token uuid not null unique default gen_random_uuid()
);

alter table public.alert_subscriptions enable row level security;

create policy "Alert subscriptions: read your own" on public.alert_subscriptions
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "Alert subscriptions: turn yours on or off" on public.alert_subscriptions
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

grant select on public.alert_subscriptions to authenticated;
grant update (enabled) on public.alert_subscriptions to authenticated;

-- ── At most 20 Saved Filters each; first one creates the subscription ───────

create function public.before_saved_filter_insert() returns trigger
  language plpgsql security definer set search_path = '' as $$
begin
  if (select count(*) from public.saved_filters where user_id = new.user_id) >= 20 then
    raise exception 'You can save up to 20 filters. Delete one to save another.'
      using errcode = 'P0001', hint = 'saved_filter_limit';
  end if;
  insert into public.alert_subscriptions (user_id) values (new.user_id) on conflict (user_id) do nothing;
  return new;
end;
$$;

revoke execute on function public.before_saved_filter_insert() from public, anon, authenticated;

create trigger saved_filters_before_insert
  before insert on public.saved_filters
  for each row execute function public.before_saved_filter_insert();
