# ADR-4879: CI renumbers a PR's migrations when max_migration.txt is its only conflict

**Status:** Accepted (built #4879; related ADR-0195, ADR-0021, ADR-0276)

**Decision.** When a push to `main` moves `max_migration.txt`, the
`migration-conflict-rebase` workflow looks at every open same-repo PR that changes the
file and is CONFLICTING. It runs `tools/auto_rebase_migration.py` on each. The script
fixes one shape only. The PR must add a single linear chain of migrations, change no
existing one, and conflict with main on `max_migration.txt` and nothing else. The new
order must also be unable to matter. No model that main's interleaved migrations
touch may be named anywhere in the chain, no model the chain touches may be named in
them, and neither side may use `RunSQL`. Renumbering runs the PR's operations after
main's. The graph check proves the final state but not what a backfill or a
constraint sees along the way, so overlapping work stays with a person. Replayed
over main's last 40 migration pairs, the gate passed 25. Several of the 15 it refused
were pairs from one PR, which never collide. When the shape holds, the script merges
main in, renames the chain to follow main's tip, and rewrites each file's one
`arxii` dependency. Then it proves the result from the index, independently of the
transform. The migrations directory must differ from main by exactly the renamed chain
plus `max_migration.txt`. Each renamed file's AST must equal the PR's original apart from
that one name. A doc that names a chain migration gets exactly that name substituted.
The graph must have one leaf and no missing migrations. The graph check has to import
the PR's code, so the work is split across two jobs. A `check` job, with no secret,
runs everything and records the merge's tree hash. A `push` job, holding a PAT
(`MIGRATION_REBASE_TOKEN`) in the main-only `migration-rebase` Environment, runs no PR
code. It re-derives the merge from the same two commits and pushes it fast-forward
only if its tree is byte-identical, so the PR's CI runs. If the queue had dropped the PR for this conflict, it re-arms auto-merge,
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
- **One job holding the token.** Stripping the token from the graph check's
  environment does not keep it from PR code running as the same user, which can read
  the parent's environment or rewrite `.git/config`.
- **Fixing every conflict.** A second conflicted file, an edited migration, or a branching
  set of migrations is a judgement call, and migrations are the riskiest change in the
  repo. Those stay with the author.
