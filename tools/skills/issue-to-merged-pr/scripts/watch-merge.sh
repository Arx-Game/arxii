#!/usr/bin/env bash
# watch-merge.sh <pr-number>
#
# Waits for an enqueued PR to leave the "waiting to merge" state, then says why
# (#4521). Run it with run_in_background right after enqueue-pr.sh, so the
# session wakes on its own when the PR merges or needs attention, instead of
# exiting at enqueue and waiting for a person to come back.
#
# "Waiting" means the PR is open, not conflicting, and either sits in the merge
# queue or has auto-merge armed (armed and awaiting approval). Polling is plain
# gh calls: no model cost while it waits.
#
# Stdout: one word, then detail.
#
# Exits:
#   0  MERGED        - run post-merge-cleanup.sh
#   1  usage, or gh failed three polls in a row
#   6  TIMEOUT       - still waiting at the cap; re-arm it (approval can take a day)
#   7  CLOSED        - closed without merging
#   8  CONFLICTING   - merge conflicts with main; merge main in, push, re-enqueue
#   9  DROPPED       - open, but neither queued nor armed (the queue ejected it,
#                      a check failed in the queue, or auto-merge was turned off)
#  10  NEEDS_ANSWER  - armed or queued, but an unresolved review thread or an open
#                      evidence challenge is holding it (#4834): fix what it flags,
#                      reply, resolve the thread or post an evidence-answer, re-enqueue
#
# Env: WATCH_MERGE_INTERVAL (seconds between polls, default 120),
#      WATCH_MERGE_CAP (seconds, default 6600: under the harness's two-hour limit on a
#      background command, so the script says TIMEOUT before anything kills it).
set -euo pipefail

usage() { echo "Usage: $0 <pr-number>" >&2; exit 1; }

[[ $# -eq 1 ]] || usage
PR="$1"
[[ "$PR" =~ ^[0-9]+$ ]] || usage

INTERVAL="${WATCH_MERGE_INTERVAL:-120}"
CAP="${WATCH_MERGE_CAP:-6600}"

# shellcheck disable=SC2016  # GraphQL variables, not shell expansions.
QUERY='query($o:String!,$r:String!,$p:Int!){repository(owner:$o,name:$r){
  pullRequest(number:$p){state mergeStateStatus reviewDecision
    autoMergeRequest{enabledAt} mergeQueueEntry{state position}
    reviewThreads(first:100){nodes{isResolved}}
    comments(last:50){nodes{body}}}}}'

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

# Emit one of: MERGED, CLOSED, CONFLICTING, NEEDS_ANSWER <detail>, UNARMED, WAITING <detail>.
# An evidence challenge is open when the NEWEST challenge comment (any verdict) says
# verdict=open and no evidence-answer comment comes after it. Both markers must open the
# comment: the challenger's own text quotes the answer marker in its instructions.
poll() {
  local json
  json=$(gh api graphql -f query="$QUERY" -f o="$OWNER" -f r="$NAME" -F p="$PR") || return 1
  jq -r '.data.repository.pullRequest
    | [(.reviewThreads.nodes // [])[] | select(.isResolved | not)] as $open_threads
    | ((.comments.nodes // []) | to_entries) as $comments
    | ([$comments[] | select(.value.body | test("^\\s*<!-- evidence-challenge"))] | last)
      as $challenge
    | ([$comments[] | select(.value.body | test("^\\s*<!-- evidence-answer")) | .key]
       | max // -1) as $answered_at
    | if .state == "MERGED" then "MERGED"
      elif .state == "CLOSED" then "CLOSED"
      elif .mergeStateStatus == "DIRTY" then "CONFLICTING"
      elif ($open_threads | length) > 0
        then "NEEDS_ANSWER \($open_threads | length) unresolved review thread(s)"
      elif $challenge != null
           and ($challenge.value.body | test("verdict=open"))
           and $challenge.key > $answered_at
        then "NEEDS_ANSWER evidence challenge open"
      elif .mergeQueueEntry != null then "WAITING queued \(.mergeQueueEntry.state) position \(.mergeQueueEntry.position)"
      elif .autoMergeRequest != null then "WAITING armed, review \(.reviewDecision)"
      else "UNARMED" end' <<<"$json"
}

elapsed=0
errors=0
unarmed=0
while :; do
  if state=$(poll); then
    errors=0
  else
    errors=$((errors + 1))
    if (( errors >= 3 )); then
      echo "ERROR gh failed $errors polls in a row" >&2
      exit 1
    fi
    state="ERROR"
  fi

  case "$state" in
    MERGED) echo "MERGED #$PR"; exit 0 ;;
    CLOSED) echo "CLOSED #$PR without merging"; exit 7 ;;
    CONFLICTING) echo "CONFLICTING #$PR conflicts with main"; exit 8 ;;
    NEEDS_ANSWER*) echo "${state/NEEDS_ANSWER/NEEDS_ANSWER #$PR:}"; exit 10 ;;
    UNARMED)
      # The queue drops its entry a moment before the merge lands, so one
      # unarmed poll is not enough; the second in a row is.
      unarmed=$((unarmed + 1))
      if (( unarmed >= 2 )); then
        echo "DROPPED #$PR is open but neither queued nor armed"
        exit 9
      fi
      ;;
    *) unarmed=0 ;;
  esac

  if (( elapsed >= CAP )); then
    echo "TIMEOUT #$PR still waiting after ${CAP}s: $state" >&2
    exit 6
  fi
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done
