# Known CI/Merge-Queue Gotchas

Symptom-keyed reference. Consult when `watch-ci.sh`, `enqueue-pr.sh`, or the merge queue behave unexpectedly — not general reading.

## `watch-ci.sh` exits 1/"ERROR" on a transient `gh` hiccup, not a CI verdict

It errors hard the moment one `gh pr view --json statusCheckRollup` call returns empty — it does not retry, and exit 1 is a generic-error code (0=OK, 5=FAIL, 6=timeout are the real verdicts). Just relaunch it. If you wrapped the call (`bash watch-ci.sh <pr>; echo "x=$?"`), the wrapper's exit masks the real one — run it as the bare background command so its true exit surfaces.

## A DIRTY/CONFLICTING PR silently stops `ci.yml` from triggering

GitHub runs `pull_request` workflows on a test-merge ref it can't build while the PR conflicts, so no run is ever created — but CodeQL/SonarCloud still run (they analyze the head ref directly), so `gh pr checks` shows a handful of green analysis checks and looks like "CI passed." `watch-ci.sh` then returns a false OK off that incomplete rollup.

**Diagnose:** `gh pr view <n> --json mergeable,mergeStateStatus` — if `CONFLICTING`/`DIRTY`, that's it.

**Fix:** re-sync with main (resolve conflicts, usually a migration renumber), push; the PR flips to `MERGEABLE` and `ci.yml` triggers within ~1 min. Verify by polling `check-runs` for the actual shard/pre-commit/frontend-test names before trusting any watch result.

## After `enqueue-pr.sh`, `autoMergeRequest` stays null — that's normal

This repo uses a GitHub merge queue, not classic auto-merge; check `mergeQueueEntry` via GraphQL instead:

```
gh api graphql -f query='{repository(owner:"Arx-Game",name:"arxii"){pullRequest(number:N){state mergedAt mergeStateStatus mergeQueueEntry{state position}}}}'
```

`mergeQueueEntry: {state: AWAITING_CHECKS, position: N}` = correctly queued (the queue re-tests on top of latest main, then merges). `mergeQueueEntry: null` while `state: OPEN` after being queued = bounced (a migration collision or failed re-test) — re-sync and re-enqueue. Don't re-enqueue repeatedly chasing `autoMerge=false`.

## A PR bounced from the queue with `PLR0915 Too many statements (52 > 50)`

Passes local `pre-commit`/ruff, but repeatedly bounced from the merge queue. Means a shared function (often a long `at_cmdset_creation`-style registration function) sat at the 50-statement ceiling and both the PR and main appended to it — the merged copy crosses the limit even though neither side does alone.

**Fix structurally:** collapse repetitive `self.add(CmdX())`-style calls into a tuple iterated with a loop, not by bumping the limit. This PR shape often also goes DIRTY (a real conflict in the same function) — merge main in, keep the loop, insert main's new entries into the tuple.
