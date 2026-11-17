#!/usr/bin/env bash
# Add Shows from event pages (TicketWeb) to the published data, and push it to the data branch.
#
#   scripts/add-event.sh URL [URL ...]               # add, commit and push to the data branch
#   scripts/add-event.sh --no-publish URL [URL ...]  # add only: review the changes in ../the_list-data yourself
#   scripts/add-event.sh --deploy URL [URL ...]      # ... and then run Deploy (skip ingestion) to publish the site
#
# Runs `python -m app.cli add-event` in the api container against the ../the_list-data worktree (database, search
# indexes, band photos), starting from origin/data. Needs LASTFM_API_KEY, DISCOGS_CONSUMER_KEY and
# DISCOGS_CONSUMER_SECRET in backend/.env, and runs only main as it is on GitHub: a migration that isn't merged would
# break the hourly ingest. It won't push while Deploy is running or once the data branch has moved: Deploy squashes
# and force-pushes it, which would drop the new Shows.
set -euo pipefail

usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
die() { echo "add-event: $*" >&2; exit 1; }

publish=1
deploy=0
urls=()
for arg in "$@"; do
  case "$arg" in
    --no-publish) publish=0 ;;
    --deploy) deploy=1 ;;
    -h|--help) usage ;;
    -*) echo "add-event: unknown option $arg" >&2; usage ;;
    *) urls+=("$arg") ;;
  esac
done
[ ${#urls[@]} -gt 0 ] || usage
[ "$publish" = 1 ] || [ "$deploy" = 0 ] || die "--deploy needs publishing; drop --no-publish"

repo="$(cd "$(dirname "$0")/.." && pwd)"
data="$repo/../the_list-data"
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"   # docker isn't on the shell's PATH
cd "$repo"

deploy_running() {
  [ -n "$(gh run list --workflow deploy.yml --limit 20 --json status \
          -q '.[] | select(.status != "completed") | .status')" ]
}

# The code that runs is main as merged.
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
  || die "check out main as it is on GitHub first (git checkout main && git pull)"
git diff --quiet HEAD -- backend || die "backend/ has uncommitted changes; this runs main as merged"

# The data worktree, from the published data.
[ "$(git -C "$data" branch --show-current 2>/dev/null)" = data ] || die "$data isn't the data branch's worktree"
[ -z "$(git -C "$data" status --porcelain)" ] \
  || die "$data has uncommitted changes; look at them, then: git -C ../the_list-data reset --hard origin/data"
deploy_running && die "Deploy is running; try again once it's done"
git -C "$data" fetch -q origin data
git -C "$data" reset -q --hard origin/data
base="$(git -C "$data" rev-parse HEAD)"
echo "add-event: from the data branch at $(git -C "$data" log --oneline -1)"

# Add the events, all or none.
docker compose up -d ollama >/dev/null 2>&1
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
if ! docker compose run --rm -T -v "$repo/backend:/src" -v "$data:/db" -w /src \
       -e DATABASE_URL=sqlite:////db/the_list.db -e FAISS_INDEX_PATH=/db/faiss -e IMAGES_PATH=/db/images \
       -e SUPABASE_URL= \
       api sh -c 'alembic upgrade head && for url in "$@"; do python -m app.cli add-event "$url" || exit 1; done' \
       sh "${urls[@]}" 2>&1 | grep --line-buffered -v "HTTP Request" | tee "$log"; then
  git -C "$data" reset -q --hard "$base"
  git -C "$data" clean -qfd images
  die "nothing added: fix the failure above and run it again"
fi

if [ "$publish" = 0 ]; then
  echo "add-event: added, not published. Review: git -C ../the_list-data status"
  echo "  publish:  git -C ../the_list-data add -A && git -C ../the_list-data commit -m '...' && git -C ../the_list-data push origin data"
  echo "  discard:  git -C ../the_list-data reset --hard origin/data && git -C ../the_list-data clean -fd images"
  exit 0
fi

# Publish: only onto the data branch this started from, with no Deploy that could force-push over it.
git -C "$data" add -A the_list.db faiss images
{ echo "Add Shows from event pages"; echo; grep '^add-event:' "$log"; } | git -C "$data" commit -q -F -
git -C "$data" fetch -q origin data
if [ "$(git -C "$data" rev-parse origin/data)" != "$base" ] || deploy_running; then
  git -C "$data" reset -q --hard "$base"
  die "the data branch moved or Deploy started while adding; nothing pushed, run it again"
fi
git -C "$data" push -q origin data
echo "add-event: pushed $(git -C "$data" log --oneline -1)"

if [ "$deploy" = 1 ]; then
  gh workflow run deploy.yml -f skip_ingest=true
  echo "add-event: Deploy started (skip ingestion); the site has the new Shows when it's done"
else
  echo "add-event: the site shows them after the next Deploy that publishes (or run this with --deploy)"
fi
