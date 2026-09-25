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

# True when a branch should be checked out in the main working tree instead of
# a linked worktree. CLAUDE.md ("Tool & Subagent Sequencing") scopes the
# worktree rule by machine: under 8 GiB of visible memory (the capped laptop:
# 6 GB VM, 4 GiB app container) one sequential agent works in place; at or
# above (the workstation) worktrees and implementer waves apply as written.
# ARXII_BRANCH_IN_PLACE=1|0 overrides the memory test either way. No
# /proc/meminfo (macOS, Windows) means "worktree".
wt_branch_in_place() {
  case "${ARXII_BRANCH_IN_PLACE:-}" in
    1) return 0 ;;
    0) return 1 ;;
  esac
  local kb
  kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || true)
  [[ -n "${kb}" && "${kb}" -gt 0 && "${kb}" -lt 8388608 ]]
}
