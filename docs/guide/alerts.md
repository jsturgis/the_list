---
title: Weekly Alerts
description: Saved Filters, the weekly Alert email, and their one-time setup.
---

People save the Shows list's filters as **Saved Filters** (the **Save search** button, or the bell on a Band or
Venue page), signing in with an emailed link. Each person can have up to 20.
After each Friday ingest they get one **Alert** email listing the Upcoming Shows that match (see
[ADR 0003](https://github.com/jsturgis/the_list/blob/main/docs/adr/0003-saved-filter-alerts-on-supabase.md)). Accounts and Saved Filters live in Supabase;
emails go through Resend from `alerts@list.sturgis.me`.

- **Commands:**
  - `python -m app.cli alerts` sends this week's Alerts. A person gets the same Alert only once a day, so running
    it again sends no one a second email.
  - `--dry-run` prints them instead, one per person whose Saved Filters match Upcoming Shows, and sends nothing. It
    needs only the two Supabase settings in `backend/.env` (see [Configuration](configuration.md#weekly-alerts)):
    `docker compose run --rm api python -m app.cli alerts --dry-run`.
  - `--only you@example.com` sends just one person's, as a test.
- **One-time setup:**
  1. **Supabase project:** email sign-in on. Site URL `https://list.sturgis.me`. Redirect URLs
     `https://list.sturgis.me/alerts/**` and `http://localhost:3000/the_list/alerts/**`; the wildcards are
     needed because the sign-in link carries the filter to save. Run `supabase/migrations/*.sql` in
     order in the SQL editor.
  2. **Resend:** verify `list.sturgis.me` (its DKIM, SPF and DMARC records are in the `sturgis.me` DNS),
     and create sending-only API keys.
  3. **Supabase SMTP:** send through Resend (`smtp.resend.com`, port 465, user `resend`), from
     `alerts@list.sturgis.me`.
  4. **GitHub:**
     - secrets `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (the `sb_secret_…` key) and `RESEND_API_KEY`, for the
       Deploy workflow's Alerts job
     - variables `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key) and
       `ALERTS_FROM`. The Deploy workflow passes the first two to the build as `PUBLIC_SUPABASE_URL` and
       `PUBLIC_SUPABASE_ANON_KEY`; set those in `frontend/.env` to try sign-in locally.
- **Unsubscribe:** every Alert links to `/alerts/unsubscribe/?token=…`, which turns that person's
  Alerts off without signing in. People can also turn them off and on, or delete alerts, on `/alerts/`.
- **Privacy:** email addresses never enter the repository, the `data` branch or the logs. The job logs
  counts only.
