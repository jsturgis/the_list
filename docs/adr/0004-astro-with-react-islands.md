# Astro, with React only where a page is interactive

The site is built with Astro instead of Next.js. It was a Next.js static export (ADR 0002), which shipped the React runtime, Next's router and a serialised copy of each page to every page, including Show, Venue and Band pages that are almost entirely text. It also needed workarounds for what static export can't do: a hand-built Band modal over `pushState`, because intercepting routes need a server, and `Suspense` around anything that read the URL so it could be prerendered. Astro renders each page to HTML at build time and loads JavaScript only for the parts marked as islands.

The existing React components are kept. Astro renders them to HTML at build time, and only the parts that change in the browser are hydrated:

- the home page's Shows list and filters (`HomeShows`), whose first page is in the HTML, with the rest loaded from `home-shows.json`
- the Alerts and Unsubscribe pages, which talk to Supabase (ADR 0003)

Everything else is static. Two small framework-free pieces of script cover what's left:

- `lib/keepFilters`, loaded by the layout, carries the Shows list's filters onto Venue links and the Back link.
- `lib/pastShows` hides Shows dated before today on pages built days earlier. The layout inlines it in `<head>`. CSS can't compare dates, so it writes a rule for each day from the export's date up to yesterday. The rules apply before anything is drawn, so past Shows never flash up, and they don't depend on any script file loading.

## Considered Options

- **Stay on Next.js static export**: no migration, but every page keeps shipping about 700 KB of JavaScript, the workarounds stay, and Next's frequent breaking changes keep landing on a site that uses none of its server features.
- **Astro with React islands**: static HTML by default, React only where a page is interactive, and the components carry over largely unchanged. Chosen.
- **Astro with the components rewritten in another UI library** (Preact, Svelte, or plain Astro components): smaller islands still, but a rewrite of every component and its tests for little gain once most pages ship no framework at all.

## Consequences

- **The Band modal is gone.** A Band link goes to the Band's page, like any other link.
- **Links between pages are full page loads.** The components use the site's own `lib/navigation` (`useQuery`, `replaceQuery`) and `lib/basePath` (`href`) rather than a framework router.
- **Very little JavaScript, measured on the fixture build at migration time:**
  - Show, Venue and Band pages load about 2 KB (the shared link script), down from about 700 KB.
  - The home page's Shows are on screen before any data loads.
- **Rendering at build time has rules:**
  - Anything that depends on the date or the URL must render the same way at build time and on the first browser render, then update.
  - Shows whose date has passed are hidden by CSS written in `<head>` (`lib/pastShows`). Lists leave out Shows dated before the export, so the rules only cover the days since. Until React takes over, the home page's "Showing N of M" still counts any hidden Shows.
  - The home page's first page is unfiltered, so CSS keeps it hidden on a filtered URL until React has every Show. That only happens when JavaScript runs (`data-js` on `<html>`, removed again if a script fails).
- **Build settings:** Supabase settings are read as `PUBLIC_SUPABASE_URL` and `PUBLIC_SUPABASE_ANON_KEY` (ADR 0003). The base path and site URL still come from `PAGES_BASE_PATH` and `PAGES_SITE_URL`.
- **Tests:**
  - Astro pages are tested by rendering them with Astro's container API, including which islands a page hydrates.
  - Components keep their React Testing Library tests.
  - The Playwright smoke tests run against the built site.
