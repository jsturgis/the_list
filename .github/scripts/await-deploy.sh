#!/usr/bin/env bash
# After the Ingest jobs workflow commits its Shows to the data branch: get a Deploy that rebuilds the site
# (skip_ingest), see it through, and record each job (ADDED, comma-separated ids) as "deploying", then "live", in
# Supabase's ingest_jobs, or "failed" when the Deploy fails.
#
# Only a manual or push-started Deploy is sure to rebuild the site: a scheduled one stops after its check when the
# List hasn't changed. So a waiting manual Deploy is followed; otherwise one is started. Starting one replaces a
# Deploy already waiting in the pages group (GitHub keeps one); a Deploy cancelled that way is replaced by
# following, or starting, the next one, up to 3 times.
#
#   ADDED=<job ids> SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... GH_TOKEN=... GH_REPO=owner/repo await-deploy.sh
set -euo pipefail
: "${ADDED:?}" "${SUPABASE_URL:?}" "${SUPABASE_SERVICE_ROLE_KEY:?}"

update() {
  curl -sf -X PATCH "${SUPABASE_URL%/}/rest/v1/ingest_jobs?id=in.($ADDED)" \
    -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H 'Content-Type: application/json' -H 'Prefer: return=minimal' \
    -d "$1" || echo "await-deploy: couldn't update the jobs: $1" >&2
}

# The oldest manual or push-started Deploy that hasn't started, or was created since $1, and isn't in $2.
next_deploy() {
  gh run list --workflow deploy.yml --limit 30 --json databaseId,status,event,createdAt --jq "
    [.[] | select(.event != \"schedule\")
         | select(.createdAt >= \"$1\" or (.status | IN(\"requested\", \"pending\", \"queued\", \"waiting\")))
         | select((.databaseId | tostring) as \$id | \"$2\" | split(\",\") | index(\$id) | not)]
    | sort_by(.createdAt) | first | .databaseId // empty"
}

followed=""
for attempt in 1 2 3; do
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  run=$(next_deploy "$since" "$followed")
  if [ -z "$run" ]; then
    gh workflow run deploy.yml --ref main -f skip_ingest=true
    for _ in $(seq 30); do
      sleep 5
      run=$(next_deploy "$since" "$followed")
      [ -n "$run" ] && break
    done
  fi
  if [ -z "$run" ]; then
    update '{"status": "failed", "message": "Added, but no Deploy could be started; the next one publishes it"}'
    exit 1
  fi

  url=$(gh run view "$run" --json url --jq .url)
  echo "await-deploy: following $url"
  update "$(jq -n --arg url "$url" '{phase: "deploying", detail: $url}')"
  gh run watch "$run" --interval 30 > /dev/null || true
  conclusion=$(gh run view "$run" --json conclusion --jq .conclusion)
  case "$conclusion" in
    success)
      update '{"status": "live", "phase": "live", "detail": null}'
      echo "await-deploy: live"
      exit 0 ;;
    cancelled)
      echo "await-deploy: $url was cancelled; following the next Deploy"
      followed="$followed,$run" ;;
    *)
      update "$(jq -n --arg url "$url" '{status: "failed", message: ("Added, but the Deploy failed: " + $url)}')"
      exit 1 ;;
  esac
done
update '{"status": "failed", "message": "Added, but three Deploys were cancelled; the next one publishes it"}'
exit 1
