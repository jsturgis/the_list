-- One-click unsubscribe from the weekly Alerts (the link in every Alert email, and its List-Unsubscribe
-- header). The site's Unsubscribe page calls this without signing in, with the token from the link; it turns
-- that person's Alerts off and keeps their Saved Filters. Returns whether the token matched anyone.
--
-- The token is taken as text, so a mangled link is just "not found" rather than an invalid-uuid error.
-- Apply by hand in the Supabase SQL editor, after 0002.

create function public.unsubscribe(token text) returns boolean
  language plpgsql security definer set search_path = '' as $$
begin
  update public.alert_subscriptions set enabled = false where unsubscribe_token::text = lower(btrim(token));
  return found;
end;
$$;

revoke execute on function public.unsubscribe(text) from public;
grant execute on function public.unsubscribe(text) to anon, authenticated;
