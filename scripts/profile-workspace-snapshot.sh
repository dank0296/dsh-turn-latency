#!/usr/bin/env bash
# Time the exact commands the dsh workspace-changes plugin runs at turn-stopping.
# Usage: bash profile-workspace-snapshot.sh /path/to/workspace
set -uo pipefail
WS=${1:?usage: profile-workspace-snapshot.sh <workspace>}
cd "$WS" || exit 1

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git repository: $WS"
  exit 1
fi

echo "workspace: $WS"
echo "HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo 'no commits (unborn branch)')"
echo "status entries (-uall): $(git status --porcelain -uall 2>/dev/null | wc -l)"
echo "untracked files under .sandboxhome: $(git status --porcelain -uall 2>/dev/null | grep -c '\.sandboxhome/' || true)"
echo "root .gitignore: $([ -f .gitignore ] && echo present || echo MISSING)"
echo

IDX=$(mktemp -u /tmp/dsh-snap-index.XXXXXX)
trap 'rm -f "$IDX"' EXIT
rm -f "$IDX"

echo "timing the snapshot into a scratch index:"
/usr/bin/time -f '  git add --all   %e s' env GIT_INDEX_FILE="$IDX" git add --all --ignore-errors
/usr/bin/time -f '  git write-tree  %e s' env GIT_INDEX_FILE="$IDX" git write-tree

echo
echo "dsh workspace-changes default timeoutMs is 30 s."
echo "If the add above is anywhere near that, each turn pays it before turn/end."
