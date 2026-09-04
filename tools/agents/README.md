# Reviewer Agents

Project-specific subagent definitions (`.claude/agents/*.md` frontmatter format),
symlinked into `~/.claude/agents/` by `.devcontainer/post-create.sh`. `.claude/`
is gitignored, so `tools/agents/` is the tracked home — same arrangement as
`tools/skills/`.

## When to add one

**Every defect that reaches `main` or production gets a reviewer agent for its
class, in the same PR as the fix.** Not a follow-up issue, not a line in a doc
nobody reads at the right moment: an agent that can be dispatched at the moment
the mistake would be repeated.

The test for whether a defect qualifies is not severity, it is *recurrence
shape* — could a competent agent make this same mistake again next week while
following the rules as written? If yes, the rules as written are the problem,
and a reviewer that reads the actual diff is the fix.

An entry here should carry, concretely:

- **the failure it exists to catch**, with the real error text, so it is
  recognizable rather than abstract;
- **why the existing gates missed it** — a defect that CI could have caught
  wants a test, not an agent;
- **what to check**, as things to look for in a diff, not principles to hold.

Pair it with a mechanical check where one is possible: the agent catches the
shape, the linter catches the instance. `reviewing-migrations` (skill) +
`tools/lint_migration_ddl_dml.py` (hook) + `migration-reviewer` (agent) is the
worked example.
