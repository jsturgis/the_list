#!/usr/bin/env bash
# A fingerprint of what the site is built from: the data branch's tree and the trees of main the build reads (the
# site, the export code and its migrations, the guides, the Deploy workflow). Trees, not commits: pruning the data
# branch rewrites its commits but not their trees. The build publishes it as deployed.json; the hourly check
# compares the live one with this, and rebuilds the site when they differ (a deploy that failed or was cancelled).
#
#   site-inputs.sh [MAIN_CHECKOUT] [DATA_CHECKOUT]     (defaults: . and data)
set -euo pipefail
main=${1:-.}
data=${2:-data}
{
  git -C "$main" rev-parse HEAD:frontend HEAD:backend/app HEAD:backend/alembic HEAD:docs/guide \
    HEAD:.github/workflows/deploy.yml
  git -C "$data" rev-parse 'HEAD^{tree}'
} | sha256sum | cut -c1-16
