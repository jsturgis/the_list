# The page fetcher

Fetches event pages for the Ingest jobs workflow from the home server's IP, which TicketWeb and Bandsintown don't
turn away (ADR 0007). It runs as a Dockge stack on TrueNAS and is reached over the tailnet at `http://truenas:8790`.

```sh
curl -s -X POST http://truenas:8790/fetch -H "Authorization: Bearer $SCRAPER_TOKEN" \
  -H 'content-type: application/json' -d '{"url": "https://www.ticketweb.com/event/..."}'
# {"status": 200, "url": "...", "html": "...", "via": "request" | "browser"}
```

## Setup, once

1. **A token.** `openssl rand -hex 32`. Add it as the GitHub secret `SCRAPER_TOKEN`
   (`gh secret set SCRAPER_TOKEN`), and keep it for the stack.
2. **The tailnet policy** (Tailscale admin console, Access controls, JSON editor). Let people's devices keep reaching
   everything, and CI only the fetcher:

   ```jsonc
   "tagOwners": { "tag:ci": ["autogroup:admin"] },
   "hosts": { "truenas": "100.114.141.123" },
   "grants": [
     { "src": ["autogroup:member"], "dst": ["*"], "ip": ["*"] },
     { "src": ["tag:ci"], "dst": ["truenas"], "ip": ["tcp:8790"] },
   ],
   ```
3. **An OAuth client** (Settings, OAuth clients, Generate): scope *Auth Keys: write*, tag `tag:ci`. Add its ID and
   secret as the GitHub secrets `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET`, and the variable
   `gh variable set SCRAPER_URL --body http://truenas:8790`.
4. **The image.** Merging to main runs the Scraper image workflow, which publishes
   `ghcr.io/jsturgis/the-list-scraper`, tagged with the commit. It takes the repository's public visibility, so
   TrueNAS pulls it without a login.
5. **The stack.** In Dockge, + Compose, name it `the-list-scraper`, paste `compose.yaml`, and in its `.env` set
   `SCRAPER_TOKEN=<the token>` and `SCRAPER_IMAGE_TAG=<the full commit hash of main>`. Deploy.

## Updating it

Set `SCRAPER_IMAGE_TAG` in the stack's `.env` to the new commit (`gh run list --workflow scraper-image.yml` shows
which commits have an image), then Deploy. The stack runs only the image it names, never `:latest`.

## What it refuses

Hardened after a pen test on 2026-11-18 (see the docstring at the top of `scraper.py`):

| Setting | Default | |
|---|---|---|
| `SCRAPER_ALLOWED_CLIENTS` | `100.64.0.0/10,fd7a:115c:a1e0::/48,127.0.0.0/8,::1/128` | who is answered: the tailnet, and the container's health check. Others get 403, though the port is published on every interface. `compose.yaml` adds the stack network's gateway, which is where TrueNAS's Tailscale app makes tailnet connections appear to come from |
| `SCRAPER_BROWSER_SITES` | `bandsintown.com,ticketmaster.com` | the sites whose challenge (Cloudflare's, or Ticketmaster's 401 "Let's Get Your Identity Verified") opens the browser. Another site's challenge is answered as it is (and the job asks for a screenshot) |
| `SCRAPER_MAX_BYTES` | 15 MB | the largest page read, decompressed |

Every address is checked as public and then connected to as checked, redirects included. In the browser, WebSockets,
service workers and WebRTC's direct connections are refused. Its log names what was refused, and why.

## Running it locally

```sh
pip install -r requirements.txt pytest httpx && patchright install chromium
SCRAPER_TOKEN=dev SCRAPER_PROFILE_DIR=./profile uvicorn scraper:app --port 8790
python -m pytest -q
```

Set `SCRAPER_HEADLESS=false` to watch the browser (on a desktop; the container has no display).
