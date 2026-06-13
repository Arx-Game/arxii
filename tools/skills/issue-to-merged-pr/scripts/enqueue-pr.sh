#!/usr/bin/env bash
# enqueue-pr.sh [--dry-run] <pr-number>
#
# Enables auto-merge (squash) on the PR. With the repo's merge queue enabled
# (#991), this hands the PR to the queue: once its required review + checks are
# satisfied, GitHub adds it to the queue, which re-tests it on top of main (and
# any earlier-queued PRs) and merges it in order. No manual re-sync with main,
# no manual merge click — the agent calls this after CI is green and exits; a
# human's approval is the only remaining gate.
#
# --auto does NOT require the PR to be mergeable yet; it arms the merge to
# happen later once requirements are met. Idempotent: a second call when
# auto-merge is already enabled is a no-op success.
#
# Exits:
#   0  auto-merge enabled (or already enabled)
#   1  usage / generic error
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi

usage() { echo "Usage: $0 [--dry-run] <pr-number>" >&2; exit 1; }
[[ $# -eq 1 ]] || usage
PR="$1"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[dry-run] gh pr merge $PR --auto --squash"
  exit 0
fi

out=$(gh pr merge "$PR" --auto --squash 2>&1) || {
  if grep -qi "already" <<<"$out"; then
    echo "auto-merge already enabled on #$PR"
    exit 0
  fi
  echo "$out" >&2
  exit 1
}
echo "auto-merge (squash) enabled on #$PR — the merge queue will merge it once approved + green"
