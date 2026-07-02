---
name: using-git-worktrees
description: "Use when starting feature work that needs isolation from the current workspace, or before executing implementation plans — ensures an isolated workspace exists."
compatibility: polytoken-only
---

# Using Git Worktrees

## Overview

Ensure work happens in an isolated workspace. Prefer the platform's native
worktree tool. Fall back to manual git worktrees only when no native tool is
available.

**Core principle:** Detect existing isolation first. Then use native tools.
Then fall back to git. Never fight the harness.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an
isolated workspace."

## Step 0: Detect Existing Isolation

**Before creating anything, check if you are already in an isolated workspace.**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

**Submodule guard:** `GIT_DIR != GIT_COMMON` is also true inside git submodules.
Before concluding "already in a worktree," verify you are not in a submodule:

```bash
# If this returns a path, you're in a submodule, not a worktree — treat as normal repo
git rev-parse --show-superproject-working-tree 2>/dev/null
```

**If `GIT_DIR != GIT_COMMON` (and not a submodule):** You are already in a
linked worktree. Skip to Step 2 (Project Setup). Do NOT create another worktree.

Report with branch state:
- On a branch: "Already in isolated workspace at `<path>` on branch `<name>`."
- Detached HEAD: "Already in isolated workspace at `<path>` (detached HEAD,
  externally managed). Branch creation needed at finish time."

**If `GIT_DIR == GIT_COMMON` (or in a submodule):** You are in a normal repo
checkout.

**Worktrees are mandatory in this repo, not optional.** The devcontainer
bind-mounts the workspace over a slow 9p filesystem; only `.claude/worktrees/`
(the `arxii-worktrees` named volume) gives `uv` a Linux-native filesystem where
it can hardlink venvs from the colocated `UV_CACHE_DIR`. Working in the main
checkout wastes ~10 min per `uv sync` and risks committing to `main` (which is
merge-queue-only — see AGENTS.md). **Do not ask for consent and do not work in
place.** Proceed directly to Step 1 to create a worktree.

## Step 1: Create Isolated Workspace

**You have two mechanisms. Try them in this order.**

### 1a. Native Worktree Tools (preferred)

You are creating an isolated workspace (Step 0 determined it's mandatory). Do
you already have a way to create a worktree? It might be a tool with a name
like `EnterWorktree`, `WorktreeCreate`, a `/worktree` command, or a
`--worktree` flag. If you do, use it and skip to Step 2.

Native tools handle directory placement, branch creation, and cleanup
automatically. Using `git worktree add` when you have a native tool creates
phantom state your harness can't see or manage.

Only proceed to Step 1b if you have no native worktree tool available.

### 1b. Git Worktree Fallback

**Only use this if Step 1a does not apply** — you have no native worktree tool
available. Create a worktree manually using git.

#### Branch already checked out? Move it into a worktree.

`pickup-issue.sh` creates the feature branch with `git branch` (it does **not**
check it out, so `main` stays put). The branch is meant to live in a worktree
on the named volume, not in the main checkout.

- **Branch exists but is NOT checked out anywhere** (the normal case after
  `pickup-issue.sh`): check it out into the worktree without `-b` (see Create
  the Worktree below).
- **You are already ON the feature branch in the main checkout** (e.g. a prior
  session checked it out): move it into a worktree. First switch `main` back
  to `main` so the branch is free, then create the worktree:
  ```bash
  git checkout main                  # free the feature branch
  git worktree add "$LOCATION/$BRANCH" "$BRANCH"
  cd "$LOCATION/$BRANCH"
  ```
  Do NOT "work in place" on the feature branch in the main checkout — that
  leaves you on the slow 9p mount and defeats the volume.

#### Directory Selection

Follow this priority order. Explicit user preference always beats observed
filesystem state.

1. **Check your instructions for a declared worktree directory preference.** If
   the user has already specified one, use it without asking.

2. **Check for an existing project-local worktree directory:**
   ```bash
   ls -d .claude/worktrees 2>/dev/null   # Preferred (named volume in devcontainer)
   ls -d .worktrees 2>/dev/null          # Fallback (hidden)
   ls -d worktrees 2>/dev/null          # Alternative
   ```
   Use the first match. `.claude/worktrees` wins because it is a Linux-native
   named volume in the devcontainer (`arxii-worktrees`), where `uv` hardlinks
   venvs from the colocated `UV_CACHE_DIR` — a worktree there sets up in under a
   second instead of ~10 min on the slow 9p bind mount. See
   `docs/devcontainer-setup.md`.

3. **If there is no other guidance available**, default to `.claude/worktrees/`
   at the project root (same reason: the named volume lives there).

#### Safety Verification (project-local directories only)

**MUST verify directory is ignored before creating worktree:**

```bash
git check-ignore -q .claude/worktrees 2>/dev/null || git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:** Add to .gitignore, commit the change, then proceed.

**Why critical:** Prevents accidentally committing worktree contents to repository.

#### Create the Worktree

```bash
# Use the BRANCH detected in Step 0 (or the current branch).
LOCATION=".claude/worktrees"   # or the existing/preferred directory from above
path="$LOCATION/$BRANCH"

# If the branch already exists (e.g. created by pickup-issue.sh but you are on
# main), check it out into the worktree WITHOUT -b:
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$path" "$BRANCH"
else
  git worktree add "$path" -b "$BRANCH"
fi
cd "$path"
```

**Sandbox fallback:** If `git worktree add` fails with a permission error
(sandbox denial), tell the user the sandbox blocked worktree creation and you're
working in the current directory instead. Then run setup and baseline tests in
place.

## Step 2: Project Setup

This repo uses `uv` and `mise`. Run the project's setup:

```bash
# Ensure uv is available and dependencies are installed
uv sync
```

The devcontainer's `post-create.sh` handles the baseline install, so in the
container this is usually a no-op or fast.

## Step 3: Verify Clean Baseline

Run tests to ensure the workspace starts clean:

```bash
# Fast tier for local iteration (SQLite)
uv run arx test --keepdb world.magic 2>/dev/null || uv run arx test world.magic

# Or the full suite if a broad baseline is warranted
uv run arx test
```

**If tests fail:** Report failures, ask whether to proceed or investigate.
Don't assume pre-existing failures are unrelated — check whether the worktree
setup (e.g., missing migration) caused them.

**If tests pass:** Report ready.

### Report

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Quick Reference

| Situation | Action |
|-----------|--------|
| Already in linked worktree | Skip creation (Step 0) |
| In a submodule | Treat as normal repo (Step 0 guard) |
| Native worktree tool available | Use it (Step 1a) |
| No native tool | Git worktree fallback (Step 1b) |
| `.claude/worktrees/` exists | Use it (named volume; verify ignored) |
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Multiple exist | Use `.claude/worktrees/` |
| None exist | Check instruction file, then default `.claude/worktrees/` |
| Directory not ignored | Add to .gitignore + commit |
| Permission error on create | Sandbox fallback, work in place |
| Tests fail during baseline | Report failures + ask |

## Arx II-specific worktree traps

These are concrete failure modes hit in this repo, beyond the generic mistakes below.

- **Absolute Read/Edit paths bypass the worktree.** In a worktree session, an
  absolute path like `/workspaces/arxii/src/...` silently reads the **main repo
  checkout**, not the worktree — even though the shell cwd is the worktree. A
  Read that contradicts `grep`/`git status` run from the worktree cwd is the
  tell. Always use the worktree-relative or worktree-absolute path
  (`/workspaces/arxii/.claude/worktrees/<branch>/src/...`); dispatched subagents
  are fine as long as their working dir is set to the worktree.
- **`EnterWorktree` + `pickup-issue.sh` leaves two branches.** `EnterWorktree`
  creates `worktree-<name>`; `pickup-issue.sh` then does
  `git checkout -b feature-<N>-<slug> origin/main` on top, so the worktree ends
  up on `feature-<N>-...` while `worktree-<name>` still exists pointing at the
  old base. Subagents can get confused by the dual-branch state and "correct"
  it by deleting the feature branch. Collapse to one branch right after pickup:
  `git branch -m worktree-<name> feature-<N>-<slug>`.
- **Never let a subagent `git checkout <sha>`.** Detaches the shared worktree's
  HEAD for everyone after it; later commits land on the detached chain while
  the feature branch stays at the old tip (only noticed when a commit prints
  `[detached HEAD ...]`). Tell subagents to inspect history via `git show`/
  `git diff` only. Recovery: `git branch -f <branch> <detached-tip>` then
  `git checkout <branch>` (works when the detached chain is linear).
- **Never `git worktree add -f <branch>` a branch already checked out
  elsewhere** (e.g. the user's own parallel-session worktree). `-f` moves the
  branch ref under the new worktree, leaving the other worktree's index stale
  — its `git status` then shows the *entire* merge as staged-in-reverse, and a
  blind commit there would revert the merge. Resolve PR conflicts on a detached
  checkout instead: `git worktree add --detach /tmp/wt origin/<branch>`, merge,
  resolve, `git push origin HEAD:<branch>` — never holding the branch ref in a
  second worktree.
- **Post-merge cleanup inside an `EnterWorktree` worktree needs a different
  path than `post-merge-cleanup.sh`** — that script's `git checkout main`
  errors because `main` is already checked out in the primary repo checkout.
  Instead: verify the merge for real (`gh pr view` state == `MERGED`), then
  `ExitWorktree(action: "remove", discard_changes: true)` (needed because a
  squash-merge leaves the branch's individual commits unmerged from the
  worktree's point of view), then from the primary checkout
  `git pull --ff-only` and `git branch -D <branch>` (force, since squash-merge
  isn't a fast-forward).

## Common Mistakes

### Fighting the harness

- **Problem:** Using `git worktree add` when the platform already provides
  isolation.
- **Fix:** Step 0 detects existing isolation. Step 1a defers to native tools.

### Skipping detection

- **Problem:** Creating a nested worktree inside an existing one.
- **Fix:** Always run Step 0 before creating anything.

### Skipping ignore verification

- **Problem:** Worktree contents get tracked, pollute git status.
- **Fix:** Always use `git check-ignore` before creating project-local worktree.

### Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues.
- **Fix:** Report failures, get explicit permission to proceed.

## Red Flags

**Never:**
- Create a worktree when Step 0 detects existing isolation.
- Use `git worktree add` when you have a native worktree tool.
- Skip Step 1a by jumping straight to Step 1b's git commands.
- Create worktree without verifying it's ignored (project-local).
- Skip baseline test verification.
- Proceed with failing tests without asking.
- Work in place in the main checkout when a worktree could be created. The slow
  9p mount makes `uv sync` ~10 min vs <2 s, and `main` is merge-queue-only.
- Check out the feature branch in the main checkout (e.g. `git checkout -b`).
  `pickup-issue.sh` uses `git branch` so the branch is free to check out into a
  worktree.

**Always:**
- Run Step 0 detection first.
- Prefer native tools over git fallback.
- Follow directory priority: explicit instructions > existing project-local
  directory > default.
- Verify directory is ignored for project-local.
- Auto-detect and run project setup.
- Verify clean test baseline.
