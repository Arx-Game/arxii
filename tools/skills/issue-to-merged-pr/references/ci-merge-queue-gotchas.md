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

## Any two migration-bearing PRs now ALWAYS collide (single-app collapse)

Since #2906 collapsed the 66 `world.*` apps into one `arxii` app, every
migration in the repo draws from ONE number sequence and ONE
`max_migration.txt`. Two in-flight PRs that each add a migration are
therefore guaranteed to conflict — first at the number (both mint `01NN_*`),
always at `max_migration.txt`. TehomCD's ruling (2026-08-05): treat this as
routine and handle it proactively, not as a surprise. On one hot afternoon a
single PR pair got bounced three times in a row (#3013 took 0111, #3010 took
0112, #3009 took 0113) — each a two-minute fix, but only if you know the
recipe.

**The fix is `rebase_migration`, not hand-renumbering.**
django-linear-migrations (the thing that makes `max_migration.txt` conflict
loudly on purpose) ships the automation:

```bash
git fetch origin main && git rebase origin/main    # conflict lands in max_migration.txt
git checkout --theirs src/world/migrations/max_migration.txt   # keep MAIN's tip...
# (direction depends on rebase orientation — the file must name MAIN's latest migration)
uv run arx manage rebase_migration arxii           # renumbers YOUR migration after main's tip,
                                                   # rewrites its dependencies + max_migration.txt
uv run pre-commit run check-migrations --all-files # verify the graph before continuing
git add src/world/migrations && git rebase --continue
git push --force-with-lease
gh pr merge <N> --auto                             # re-arm; the queue entry died with the bounce
```

**Proactively, before every enqueue** (and after any long CI wait): compare
your branch's new migration number against main's tip —

```bash
git fetch origin main --quiet
git show origin/main:src/world/migrations/max_migration.txt
```

If main's tip number ≥ yours, run the recipe above BEFORE the queue bounces
you — the queue's trial merge will hit the same conflict you can fix in two
minutes now.

**Stacked PRs renumber as a chain**: rebase the parent first (its migration
gets the next free number), then rebase the child onto the parent's new tip
and `rebase_migration` again — the child's migration depends on the parent's
renamed one, so the parent must settle first.

## A PR bounced from the queue with `PLR0915 Too many statements (52 > 50)`

Passes local `pre-commit`/ruff, but repeatedly bounced from the merge queue. Means a shared function (often a long `at_cmdset_creation`-style registration function) sat at the 50-statement ceiling and both the PR and main appended to it — the merged copy crosses the limit even though neither side does alone.

**Fix structurally:** collapse repetitive `self.add(CmdX())`-style calls into a tuple iterated with a loop, not by bumping the limit. This PR shape often also goes DIRTY (a real conflict in the same function) — merge main in, keep the loop, insert main's new entries into the tuple.
