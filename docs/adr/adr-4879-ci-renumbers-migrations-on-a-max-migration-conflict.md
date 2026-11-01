# ADR-4879: CI renumbers a PR's migrations when max_migration.txt is its only conflict

**Status:** Accepted (built #4879; related ADR-0195, ADR-0021, ADR-0276)

**Decision.** When a push to `main` moves `max_migration.txt`, the
`migration-conflict-rebase` workflow looks at every open same-repo PR that changes the
file and is CONFLICTING. It runs `tools/auto_rebase_migration.py` on each. The script
fixes one shape only: the PR adds a single linear chain of migrations, changes no
existing one, and conflicts with main on `max_migration.txt` and nothing else. It
merges main in, renames the chain to follow main's tip, and rewrites each file's one
`arxii` dependency. Then it proves the result from the index, independently of the
transform. The migrations directory must differ from main by exactly the renamed chain
plus `max_migration.txt`. Each renamed file's AST must equal the PR's original apart from
that one name. The graph must have one leaf and no missing migrations. On success it
pushes the merge commit fast-forward with a PAT (`MIGRATION_REBASE_TOKEN`), so the PR's
CI runs. If the queue had dropped the PR for this conflict, it re-arms auto-merge,
unless the PR carries review evidence. Anything else is refused with a PR comment, and
nothing is pushed.

**Why:** the single-app collapse (ADR-0195) made every pair of migration-bearing PRs
collide. Each merge then dropped the next PR from the queue until someone ran the manual
`rebase_migration` recipe (#4826, #4828 and #4832 in one afternoon). The answer is
mechanical, so a person spending a turn on it is pure churn.

**Rejected alternatives.**

- **Calling `django-linear-migrations`' `rebase_migration` directly.** It handles one
  migration. On a chain it re-points the tip and orphans the rest. It also guesses the
  sides from `MERGE_HEAD`, which a hand swap once double-flipped (2026-09-15). The
  schema/data split rule makes chains the common case: #4862 shipped 0347 and 0348. The
  script applies the same dependency rewrite link by link, with both sides read from the
  refs. The postconditions, not the transform, carry the safety claim.
- **Rebasing and force-pushing.** That rewrites published history and the evidence
  screenshot URLs that point into it.
- **Pushing with `GITHUB_TOKEN`.** Its pushes trigger no `pull_request` workflows, so the
  PR would sit with no required checks on its new head.
- **Fixing every conflict.** A second conflicted file, an edited migration, or a branching
  set of migrations is a judgement call, and migrations are the riskiest change in the
  repo. Those stay with the author.
