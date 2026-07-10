# shellcheck shell=bash
# _wt-helpers.sh — sourced by sync-with-main.sh and post-merge-cleanup.sh.
#
# Both scripts must operate on a *specific* checkout regardless of the caller's
# cwd: an agent may invoke them from the shared main checkout, from the branch's
# own worktree, or from an unrelated worktree. The old code used bare
# `git checkout <branch>` / `git checkout main`, which mutates whatever checkout
# the caller happens to stand in — and fails outright when the target branch is
# already checked out in another worktree ("fatal: '<branch>' is already checked
# out at ..."). These helpers resolve the right directory so callers can use
# `git -C <dir>` explicitly (#2060).
#
# Not executable on its own — source it. All functions are pure reads.

# Path of the primary (non-linked) working tree. `git worktree list --porcelain`
# always lists the main working tree first, so the first `worktree` line wins.
wt_main_path() {
  git worktree list --porcelain | awk '/^worktree /{print $2; exit}'
}

# Path of the worktree that currently has <branch> checked out, or empty string
# if the branch is not checked out in any worktree. Blocks in the porcelain
# output are `worktree <path>` ... `branch refs/heads/<name>`, so track the most
# recent worktree path and print it when its branch line matches.
wt_for_branch() {
  local target="refs/heads/$1"
  git worktree list --porcelain | awk -v t="$target" '
    /^worktree /{wt=$2}
    /^branch /{if ($2==t){print wt; exit}}
  '
}
