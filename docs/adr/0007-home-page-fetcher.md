# Event pages are fetched from the home server, over Tailscale

An ingest job's link was fetched from the GitHub runner that runs the Ingest jobs workflow (ADR 0006), and every one
failed: TicketWeb answers GitHub's runners with Cloudflare's 530, and Bandsintown with Cloudflare's block page. The
same requests from a home IP succeed: TicketWeb's page comes straight from its own server, and Bandsintown's passes
Cloudflare once a browser has (or straight away, often). So the only way to add a Show from those sites was a
screenshot, read by a vision model and checked by hand.

Now the page is fetched by a **page fetcher on the home server** (`scraper/`), a container in Dockge on TrueNAS. The
workflow joins the tailnet and asks it for the page:

```
Ingest jobs workflow ── tailscale/github-action (ephemeral, tag:ci) ──▶ POST http://truenas:8790/fetch {url}
  page fetcher (home IP) ── curl_cffi, as Chrome ──▶ the site
                         └─ Cloudflare challenged it ──▶ Patchright (headless, Chrome's user agent) ──▶ the site
```

## Decisions

- **Only the fetch moves.** The job still runs on GitHub, so it doesn't depend on a machine at home being awake for
  anything else, and the readers (`app/ingestion/ticketweb.py`, `app/ingestion/event_page.py`) still read the HTML.
  `app/ingestion/page_fetch.py` asks the fetcher when `SCRAPER_URL` is set, else fetches directly as before; if the
  fetcher can't be reached it fetches directly too, and a page that still can't be read asks for a screenshot.
- **curl_cffi first, the browser when Cloudflare asks.** Most pages need nothing more than a request that looks like
  Chrome down to its TLS handshake. When Cloudflare challenges it (`cf-mitigated: challenge`, or its "Just a moment" or
  "Attention Required" page), the page is opened in one long-lived Patchright browser, headless. The cookies it earns
  (`cf_clearance`) go back to curl_cffi, so the site's next pages need no browser until they run out.
- **Both tiers are one client: the browser's.** Cloudflare ties cf_clearance to the client it gave it to, and looks for
  a user agent that disagrees with the client hints or with the platform the browser's scripts report. So the user agent
  is the browser's own, read when the service starts, with "HeadlessChrome" (blocked outright) made "Chrome"; curl_cffi
  sends it and the browser's client hints (`sec-ch-ua`...), over the TLS handshake of the nearest Chrome version it can
  imitate. A hard-coded Windows Chrome 156 user agent had curl_cffi's `sec-ch-ua` saying Google Chrome 152 beside it,
  and the browser saying Windows from a Linux container.
- **The tailnet policy lets CI reach the fetcher and nothing else.** The runner joins as an ephemeral node tagged
  `tag:ci`, from a Tailscale OAuth client, and the policy grants `tag:ci` only `truenas:8790`. People's own devices keep
  the access they had.
- **The fetcher only fetches public pages.** Every address a URL resolves to, for the page, each redirect and every
  request the browser makes, must be public: the home network, the tailnet and the server itself are refused. It also
  wants a bearer token (`SCRAPER_TOKEN`), so a device on the tailnet can't use it as a proxy without one.
- **Hardened after a pen test (2026-11-18).** It found that the address check could be beaten by DNS rebinding
  (checked public, connected private), that a site could fake a Cloudflare challenge to get its page run in the browser,
  where WebSockets weren't checked, that a small gzip bomb exhausted the container's memory, and that the whole home
  network could reach the port. Now curl_cffi connects to the address it checked, the browser opens only for
  `SCRAPER_BROWSER_SITES` (Bandsintown) and refuses WebSockets, service workers and direct WebRTC, a page is read to
  15 MB decompressed, and only the tailnet and the container itself are answered. Errors no longer say what was found
  behind the server, the API docs are off, and every dependency, the base image, the deployed image and the actions
  holding secrets are pinned. Still open: Chromium runs without its own sandbox (the container is the boundary), the
  browser resolves names itself for Bandsintown's pages, and nothing limits the container's egress to the home
  network at the network level.
- **Venue calendars go through it too (2026-11-18).** The hourly Deploy workflow joins the tailnet the same way, and
  `app/ingestion/venue_calendar.py` asks the fetcher for each Venue's homepage and calendar page
  (`page_fetch.from_scraper`, which keeps the site's own status, so a calendar that's gone (404) is still told from
  one that's down). Some Venues' sites answered the runner's plain request with 403. Checking that a calendar link
  resolves still sends a HEAD directly, and a refused one is asked again with GET, through the fetcher. If the fetcher
  can't be reached, the pages are fetched directly as before, so the ingest never waits on the home server.
- **The image is built by GitHub** (`.github/workflows/scraper-image.yml`) and published as
  `ghcr.io/jsturgis/the-list-scraper`; the Dockge stack (`scraper/compose.yaml`) pulls it.

## Considered options

- **Patchright on the GitHub runner**: the runner's IP is the problem, not its browser. TicketWeb's 530 isn't a
  challenge a browser can pass.
- **A self-hosted GitHub runner at home**: fixes the IP, but every job would wait on the home server, and the Ollama
  models and Python environment would live there too.
- **A residential proxy**: pays someone for what the home connection already gives.
- **A bookmarklet that sends the open page's HTML**: no fetching at all, but only from a desktop browser, and a new way
  to add Shows to build on the Admin page. It may still be worth having.

## Consequences

- Setup, once: see `scraper/README.md` (the tailnet policy, an OAuth client, the secrets, the Dockge stack).
- When the home server or its connection is down, links fail as they did before and ask for a screenshot.
- Sites change what they block. When a site starts failing, the fetcher's log says whether it went by request or
  browser and what came back.
