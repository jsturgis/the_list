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
   `ghcr.io/jsturgis/the-list-scraper`. Make the package public once (GitHub, Packages, the-list-scraper, Package
   settings) so TrueNAS can pull it without a login.
5. **The stack.** In Dockge, + Compose, name it `the-list-scraper`, paste `compose.yaml`, and set
   `SCRAPER_TOKEN=<the token>` in its `.env`. Create `/mnt/store/the-list-scraper/data` owned by 568:568 first.
   Deploy. To update it later, Dockge's Update pulls the newest image.

## Running it locally

```sh
pip install -r requirements.txt pytest && patchright install chromium
SCRAPER_TOKEN=dev SCRAPER_PROFILE_DIR=./profile uvicorn scraper:app --port 8790
python -m pytest -q
```

Set `SCRAPER_HEADLESS=false` to watch the browser (on a desktop; the container has no display).
