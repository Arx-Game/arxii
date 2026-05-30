---
name: github-operations
description: Use before any GitHub operation via the gh CLI — creating/editing/closing/commenting on issues or PRs, assigning, labelling, or referencing an issue/PR number. Especially right after gh issue create / gh pr create when you need the new number, or when about to mutate an issue you "know" the number of.
---

# GitHub Operations (gh CLI)

## Overview

**Read the identifier the command gave you; never compute it.** GitHub issue and PR
numbers are a single shared sequence across the whole repo — issues AND pull requests
draw from it. So the number after the last one you saw is almost never the one you just
created. The only source of truth for "what number did this get" is the output of the
command that created it.

This skill is permanent good practice (not a harness-bug workaround). It exists because
agents repeatedly (a) assume `gh issue create` made issue *N+1* after seeing issue *N*,
and (b) edit/comment/close an issue whose title they assumed from its number — both of
which mutate the WRONG issue.

## The core rule

`gh issue create` and `gh pr create` print the canonical URL of the thing they made,
e.g. `https://github.com/owner/repo/issues/651`. **The number in that URL is the
answer.** Use it verbatim. Do not add 1. Do not infer it from the last issue you listed.
Do not assume issues and PRs have separate counters — they share one.

```bash
# create prints: https://github.com/Arx-Game/arxii/issues/651
gh issue create --title "..." --body "..."   # ← the URL says 651, so it IS 651
gh issue view 651 --json number,title         # ← verify 651, NOT 652
```

## Gates

1. **Capture the returned number.** After `gh issue create` / `gh pr create`, read the
   URL it printed and use that exact number. If you piped the output away and didn't see
   the URL, run `gh issue list --limit 1 --json number,title` (or `gh pr list`) to find
   it — do not guess.
2. **Verify number↔title before any mutation.** Before `gh issue comment/edit/close`,
   `--add-label`, `--add-assignee` (or PR equivalents), run `gh issue view <n> --json
   number,title` and confirm the title matches your intent **in the same turn as the
   write**. Numbers are not guessable; a remembered title may be stale.
3. **One write per message; verify after.** Issue/PR mutations are state changes — emit
   one, observe its result, then the next. Don't batch multiple mutations (or a mutation
   with the reads that inform it) in one message.
4. **Issues and PRs share a counter.** Creating a PR can consume the number you expected
   for an issue and vice-versa. Never reason "the next issue will be N+1."
5. **Wait on CI with a single waiter.** To watch a PR's checks, arm ONE background waiter
   (`until [ "$(gh pr view <n> --json statusCheckRollup -q '[.statusCheckRollup[] |
   select(.status!="COMPLETED")] | length')" = "0" ]; do sleep 30; done`) — don't run
   several overlapping pollers, and don't chain `sleep N && gh ...` (the harness blocks
   it; use a background `until` loop or Monitor).
6. **Read-only `gh` is safe to batch; writes are not.** `gh issue view`, `gh pr checks`,
   `gh api` GETs can run freely. Anything that changes server state follows gates 1–3.

## Quick reference

| Operation | Command | Get the number from |
|---|---|---|
| New issue | `gh issue create --title … --body …` | the printed `/issues/<n>` URL |
| New PR | `gh pr create --base main --head <branch> …` | the printed `/pull/<n>` URL |
| Verify before edit | `gh issue view <n> --json number,title` | confirm title matches intent |
| Comment | `gh issue comment <n> --body …` | only after verifying <n>'s title |
| Label/assign | `gh issue edit <n> --add-label … --add-assignee …` | only after verifying <n> |
| Find a just-made number | `gh issue list --limit 1 --json number,title` | if you lost the create URL |

## Red flags — STOP

- You're about to query/edit issue *N+1* because you just saw or made *N*. (Read the URL.)
- You're commenting on / closing an issue without viewing its title this turn.
- You assumed issues and PRs have independent numbering.
- You're firing several `gh` mutations in one message, or a `sleep N && gh` chain.

| Rationalization | Reality |
|---|---|
| "I just made #N, so this is #N+1" | The create URL gave the real number. Numbers are shared across issues+PRs; N+1 is usually something else. |
| "I remember that issue's title" | Titles drift and memory is wrong. `gh issue view` it before mutating. |
| "Batching the gh writes is faster" | One wrong-target write costs far more than the extra messages. One write, verify, next. |
| "The number is obviously sequential" | It isn't. Read the returned URL. |

## Real-world impact

In a 2026-05-30 session an agent repeatedly created an issue (URL `.../issues/651`) and
then queried `652`, every time — a consistent off-by-one from computing the number
instead of reading the returned URL. Earlier the same lineage clobbered issue #629 by
editing an issue whose title it assumed from its number. Both are fixed by one habit:
take the identifier from the command's own output, and verify number↔title before any
mutation.
