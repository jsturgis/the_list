-- The weekly Alerts job (python -m app.cli alerts) reads every Saved Filter and Alert subscription with the
-- project's secret key, as the service_role. That role bypasses row-level security, but the project was
-- created with "Automatically expose new tables" off, so it still needs table privileges. Read only:
-- unsubscribing goes through its own function.
--
-- Apply by hand in the Supabase SQL editor, after 0001_saved_filters.sql.

grant select on public.saved_filters to service_role;
grant select on public.alert_subscriptions to service_role;
