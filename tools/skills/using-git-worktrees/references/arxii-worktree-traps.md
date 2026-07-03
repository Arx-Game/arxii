# Arx II-Specific Worktree Traps

Concrete failure modes hit in this repo. Consult this when you recognize one of the symptoms below — not general reading.

## Absolute Read/Edit paths bypass the worktree

**Symptom:** a `Read` contradicts `grep`/`git status` run from the worktree cwd.

In a worktree session, an absolute path like `/workspaces/arxii/src/...` silently reads the **main repo checkout**, not the worktree — even though the shell cwd is the worktree. Always use the worktree-relative or worktree-absolute path (`/workspaces/arxii/.claude/worktrees/<branch>/src/...`); dispatched subagents are fine as long as their working dir is set to the worktree.

## `EnterWorktree` + `pickup-issue.sh` leaves two branches

**Symptom:** a subagent gets confused by a dual-branch state and "corrects" it by deleting the feature branch.

`EnterWorktree` creates `worktree-<name>`; `pickup-issue.sh` then does `git checkout -b feature-<N>-<slug> origin/main` on top, so the worktree ends up on `feature-<N>-...` while `worktree-<name>` still exists pointing at the old base.

**Fix:** collapse to one branch right after pickup: `git branch -m worktree-<name> feature-<N>-<slug>`.

## Never let a subagent `git checkout <sha>`

**Symptom:** a commit prints `[detached HEAD ...]`.

Detaches the shared worktree's HEAD for everyone after it; later commits land on the detached chain while the feature branch stays at the old tip. Tell subagents to inspect history via `git show`/`git diff` only.

**Recovery:** `git branch -f <branch> <detached-tip>` then `git checkout <branch>` (works when the detached chain is linear).

## Never `git worktree add -f <branch>` a branch checked out elsewhere

**Symptom:** another worktree's (e.g. the user's own parallel-session worktree) `git status` suddenly shows the *entire* merge as staged-in-reverse.

`-f` moves the branch ref under the new worktree, leaving the other worktree's index stale. A blind commit there would revert the merge.

**Fix:** resolve PR conflicts on a detached checkout instead: `git worktree add --detach /tmp/wt origin/<branch>`, merge, resolve, `git push origin HEAD:<branch>` — never holding the branch ref in a second worktree.

## Post-merge cleanup inside an `EnterWorktree` worktree

**Symptom:** `post-merge-cleanup.sh`'s `git checkout main` errors, because `main` is already checked out in the primary repo checkout.

**Fix:** verify the merge for real (`gh pr view` state == `MERGED`), then `ExitWorktree(action: "remove", discard_changes: true)` (needed because a squash-merge leaves the branch's individual commits unmerged from the worktree's point of view), then from the primary checkout `git pull --ff-only` and `git branch -D <branch>` (force, since squash-merge isn't a fast-forward).
