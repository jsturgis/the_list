# Saved Filters and Alerts on Supabase, sent through Resend

People can save the filters they use on the Shows list and get a weekly Alert email with the Upcoming Shows that match. That needs accounts, a place the browser can write Saved Filters to, and a way to send email, none of which a static site on GitHub Pages has (ADR 0002). Accounts and Saved Filters live in **Supabase**, which the browser calls directly. Its email sign-in links verify each address, and row-level security keeps each person's Saved Filters private, so its public key can ship in the site. The weekly Alerts are built in the Deploy workflow after the ingest and sent through **Resend** from `list.sturgis.me`.

This amends ADR 0002 only for accounts and Saved Filters: Show data still comes from the static export, and the site still builds and serves with Supabase down. Its Alerts features are just unavailable.

## Considered Options

- **Supabase**: hosted Postgres with an API the browser can call, row-level security, and email sign-in links. The free tier is enough. Chosen.
- **A Cloudflare Worker with D1**: an API we'd write ourselves: CORS, validation, and verification emails. More code to own.
- **Firebase**: similar to Supabase but a document store with a heavier client library, and a less natural fit for the SQL-shaped filters.
- **For sending**:
  - **Resend** was chosen: free tier, built for automated mail, published limits, and DKIM/SPF on a subdomain we control.
  - **Gmail SMTP** works without a domain, but sends as a personal address with daily limits.
  - **Proton's free plan** has no SMTP or Bridge. Its paid SMTP doesn't publish its limits.
  - **Amazon SES** needs the most setup.
  - `jsturgis.github.io` can't hold mail DNS records, so a domain we control (`sturgis.me`) was needed regardless.

## Consequences

- The schema lives in `supabase/migrations/` and is applied by hand in the Supabase SQL editor. The project has "Automatically expose new tables" off and automatic RLS on, so every table needs explicit grants and policies.
- **Keys:**
  - The site's build needs `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key). Without them the Alerts features are hidden.
  - The Alerts job needs the secret key and the Resend key as GitHub secrets.
- Sign-in uses the implicit flow, so an emailed link works on a different device from the one that asked for it.
- Email addresses and Saved Filters never enter the repository or the `data` branch. The Alerts job reads them at run time and logs counts only.
- Supabase's own sign-in emails go through Resend's SMTP, because the built-in sender allows only a few an hour.
