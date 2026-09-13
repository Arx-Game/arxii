# ADR-0296: The commit hook never clears the worktree, so implementers can share one

pre-commit's generated hook runs `git checkout -- .` over the whole worktree while a
commit's hooks run, which removed, and could permanently lose, a sibling agent's
uncommitted work (#3787, reproduced in #3814); that was why implementer subagents were kept
strictly serial. We replaced the installed hook with `tools/githooks/pre-commit`, which runs
`pre-commit run --files` on the staged files, treats a failure caused only by files outside
the commit as a pass, re-stages auto-fixes only for fully staged files, and is installed as
a shim in the shared `.git/hooks`, so CLAUDE.md now lets up to three implementers share a
worktree when their plan tasks' file lists do not overlap. Rejected: a worktree per
implementer (heavy, and read-only agents never needed one), a commit helper agents must
remember to call (protects only the agents that use it), file locks or a claims board (go
stale and make agents wait), `core.hooksPath` (`.git/config` is shared with the Windows
host), and staying serial (costs wall-clock on every multi-task plan once the cause is
fixed); the price is that hooks read staged files as they are on disk rather than the exact
staged snapshot, so an auto-fix on a partly staged file refuses the commit, while CI's
required `pre-commit` check still runs on exactly what was committed.

> Status: accepted · Source: issue #3814
