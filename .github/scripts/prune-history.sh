#!/usr/bin/env bash
# Keep only the newest N commits of the current branch (default 4: the current data plus 3 to roll
# back to). Everything older is squashed into the oldest kept commit, which becomes the new root.
# Each kept commit keeps its tree, message, author and dates. Prints the new head.
#
#   prune-history.sh [N]     then: git push --force-with-lease origin HEAD:<branch>
set -euo pipefail
keep=${1:-4}

count=$(git rev-list --count HEAD)
if [ "$count" -le "$keep" ]; then
  echo "history has $count commits (keeping up to $keep): nothing to prune" >&2
  git rev-parse HEAD
  exit 0
fi

parent=""
for commit in $(git rev-list --reverse --max-count="$keep" HEAD); do
  message=$(git log -1 --format=%B "$commit")
  [ -z "$parent" ] && message="$message

(Older history squashed: the data branch keeps only its newest $keep commits.)"
  parent=$(
    GIT_AUTHOR_NAME=$(git log -1 --format=%an "$commit") GIT_AUTHOR_EMAIL=$(git log -1 --format=%ae "$commit") \
    GIT_AUTHOR_DATE=$(git log -1 --format=%aI "$commit") GIT_COMMITTER_DATE=$(git log -1 --format=%cI "$commit") \
    git commit-tree "$commit^{tree}" ${parent:+-p "$parent"} -m "$message"
  )
done

git reset -q --soft "$parent"
echo "pruned history from $count to $keep commits" >&2
git rev-parse HEAD
