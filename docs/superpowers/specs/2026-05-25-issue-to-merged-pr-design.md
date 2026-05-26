# issue-to-merged-pr Skill — Design

**Date**: 2026-05-25
**Status**: Brainstormed, awaiting spec review
**Branch**: `devcontainer-workflow-skill`

## Purpose

A team-wide Claude Code skill that takes a GitHub issue (or an interactive
prompt) and carries it through to a merged PR with minimal human gating.
Lives in version control so both maintainers use the same workflow inside the
devcontainer.

The skill replaces an older personal habit (review-diff-then-push) with a
GitHub-PR-centric review surface: agent does the work, opens a PR, human
reviews on GitHub, agent addresses comments and CI failures, deferred work is
captured as GitHub issues (not roadmap entries, not code TODOs).

## Lifecycle

```
START
  └── Pickup: user provides issue number OR no arg (interactive prompt → agent files an issue then proceeds)
  └── Determine type from issue labels (feature, fix, chore, refactor, test, docs, perf, ...) — falls back to interactive prompt if no label
  └── Branch named <type>-<N>-<slug>  (e.g. fix-47-migration-history, feature-52-clash-side-favored)
  └── Design (substantive work only — skipped for trivial issue types):
       superpowers:brainstorming → spec → superpowers:writing-plans → plan
  └── Implementation: per plan
  └── Sync-with-main: fetch origin/main; rebase; resolve conflicts
       └── for each conflict whose files overlap with another open issue's domain,
           the agent files/updates a comment on that issue explaining how the resolution
           interacts with their work
  └── Push & open PR; body says "Closes #N" + lists deferred follow-ups (filed as issues NOW and linked)
  └── CI watch loop (smart cadence):
       └── poll cheap checks (lint, frontend) within ~90s of push
       └── back off to ~3-5 min intervals for backend tests
       └── on failure: read failure log, attempt fix, push, restart cadence
       └── stop after 3 attempts on the same (check-name, failure-signature) OR 5 total pushes on this PR → diagnostic PR comment, await human (see Bail conditions)
  └── (Session ends here — review on GitHub is async)
  └── PR-comment phase (re-invocation): agent reads PR comments, addresses each, pushes, returns to CI watch
  └── Conflict-during-review phase: if main has moved or user requests rebase, agent re-syncs and re-comments cross-issue impacts
  └── Post-merge cleanup (re-invocation): checkout main, pull, delete local branch, verify auto-close, comment on linked-but-unclosed issues, file review-driven new follow-ups
END
```

The skill is **multi-invocation**. A single agent session typically does
Pickup→Push, then exits while CI runs and human review is async. The user
re-invokes the skill in a new session pointing at the PR; the agent reads PR
state and picks up the right phase. No persistent on-disk workflow state —
GitHub holds the truth.

### Phase detection on re-invocation

When invoked against an existing PR (`/issue-to-merged-pr 47` where the branch
already has an open PR, or `/issue-to-merged-pr` with no arg and the current
branch matches the convention), the agent runs `gh pr view --json
state,merged,merged_at,statusCheckRollup,reviewDecision,mergeStateStatus`
first, then — only if checks are all-success and the PR is open — calls
`read-pr-comments.sh` to populate the unread-comments cell. Phase is picked
from this table (rows evaluated top-to-bottom; first match wins):

| `state` | `merged` | `mergeStateStatus` | `statusCheckRollup` aggregate | unread-comments | Phase |
|---|---|---|---|---|---|
| `MERGED` | `true` | — | — | — | **Post-merge cleanup** |
| `CLOSED` | `false` | — | — | — | **Closed-without-merge** (notify user, exit) |
| `OPEN` | `false` | `DIRTY` / `BEHIND` | — | — | **Conflict-during-review** (re-sync with main, re-run cross-issue overlap, push) |
| `OPEN` | `false` | — | any failure | — | **CI fix** (read failures, fix, push, return to CI watch) |
| `OPEN` | `false` | — | any pending | — | **CI watch** (resume `watch-ci.sh`) |
| `OPEN` | `false` | — | all success | exist | **PR-comment** (address comments, push, bump marker) |
| `OPEN` | `false` | — | all success | none | **Idle** (post status comment, exit — review is on human) |

"Unread comments" is defined per the `read-pr-comments.sh` marker mechanism
(see Script contracts). The agent never has to ask the user "where are we" —
the phase is a pure function of GitHub state.

If the current branch has no open PR but matches the convention
`<type>-<N>-<slug>`, the agent is mid-implementation and resumes from the
Implementation step of the lifecycle (continuing the plan).

## File layout

```
tools/skills/issue-to-merged-pr/
├── SKILL.md                              # recipe, decision logic, when to use, examples
├── README.md                             # human-facing docs (includes bare-metal Setup)
├── spec-document-reviewer-prompt.md      # project-local override of superpowers' canonical reviewer prompt (see Spec-review override)
├── scripts/
│   ├── pickup-issue.sh                   # superpowers-installed precheck, then fetch issue, infer type, create branch
│   ├── sync-with-main.sh                 # fetch + rebase, report conflicts + cross-issue overlap
│   ├── open-pr.sh                        # push, open PR with body template
│   ├── file-followup.sh                  # create a new issue, return its number
│   ├── comment-on-issue.sh               # post a comment to an existing issue
│   ├── watch-ci.sh                       # smart-cadence polling loop, exits when checks settle
│   ├── get-ci-failure.sh                 # given a failing check, fetch concise diagnostic logs
│   ├── read-pr-comments.sh               # fetch comments newer than last-addressed marker
│   └── post-merge-cleanup.sh             # checkout main, pull, branch delete, related-issue actions
└── templates/
    ├── pr-body.md                        # PR body template (Closes / Follow-ups / Notes)
    └── followup-issue.md                 # follow-up issue body template
```

### Script contracts

Each script is pure bash (no embedded Python — per repo-wide rule), uses `gh`
+ `git` + standard POSIX tools, accepts arguments as documented below, emits
JSON on stdout where structured output is needed, and supports `--dry-run` on
the state-mutating ones.

- **pickup-issue.sh** `<issue-number>` → first runs the superpowers precheck (exits 2 with install command if missing; see Plugin dependency); then fetches the issue, infers type from labels, emits JSON `{type, slug, branch, parent_issue_url}`; creates branch from `origin/main`; errors if issue is closed or assigned to a different user.
- **sync-with-main.sh** `<branch>` → `git fetch origin && git rebase origin/main`; on conflict emits JSON listing conflicted files and any open issues whose body/comments substring-match those file paths (over-inclusive on purpose).
- **open-pr.sh** `<branch> <issue-number> <followup-issue-numbers...>` → pushes (with `--force-with-lease` if branch was rebased), opens PR via `gh pr create` with body composed from `templates/pr-body.md`; emits PR number. `--dry-run` prints the body without pushing.
- **file-followup.sh** `<title> <body-path> <labels...>` → `gh issue create`; emits issue number. `--dry-run` prints the title/body/labels.
- **comment-on-issue.sh** `<issue-number> <body-path>` → `gh issue comment`. `--dry-run` prints the comment.
- **watch-ci.sh** `<pr-number>` → blocks with internal `sleep` calls per cadence below; exits when checks settle. Stdout: `OK` or `FAIL <check-name>`. **Idempotent across sessions:** on start, queries `gh pr checks` first; if no checks are pending, exits immediately with the current rollup status (no sleep). This makes re-invocation while a prior session's CI is mid-run safe — the new session walks straight into the right phase via the phase-detection table rather than racing a stale watch. There is no inter-session lock: GitHub is the single source of truth, multiple agents querying it concurrently is harmless.
- **get-ci-failure.sh** `<pr-number> <check-name>` → emits last ~200 lines of failing job log + failure summary.
- **read-pr-comments.sh** `<pr-number>` → emits unread comments — those authored after the comment ID recorded in the PR body's marker `<!-- last-addressed-comment: <id> -->`. If the marker is missing, all comments are returned. Fetches both issue-style PR comments (`gh api repos/:owner/:repo/issues/:pr/comments`) and review-thread comments (`gh api repos/:owner/:repo/pulls/:pr/comments`); merges by `created_at`. After the agent addresses comments and pushes, it updates the marker to the highest-seen comment ID via `gh pr edit --body` (preserving the rest of the body). This avoids the fragility of timestamp-relative-to-commit filtering: a tiny follow-up push doesn't make older unaddressed comments disappear, and a force-push doesn't reset the marker.
- **post-merge-cleanup.sh** `<branch> <pr-number>` → switches to main, pulls, deletes branch; emits JSON of linked-issue actions taken. `--dry-run` prints actions without performing them. **Dirty-tree handling:** if the working tree has uncommitted changes when the script is invoked, it exits non-zero with a structured error naming the dirty files — never stashes, never resets. This is deliberate: the user (or a parallel agent session) may have started unrelated work; silently stashing or discarding it loses that work. The agent then surfaces the message to the user and waits for them to commit, stash, or discard explicitly. **Branch deletion after squash-merge:** the script tries `git branch -d <branch>` first; if it fails (the squash-merge commit on `main` doesn't contain the feature branch's commits as ancestors, so safe-delete reliably fails after squash), the script then verifies the PR is `merged: true` via `gh pr view --json merged` and falls back to `git branch -D`. If `merged` is `false`, the script aborts without forcing — that state means cleanup was invoked prematurely.

### Templates

`templates/pr-body.md`:

```markdown
Closes #{{issue_number}}

## Summary

{{summary}}

## Follow-ups filed

{{followup_list}}

## Notes

- Brainstorm/plan: {{ran_or_skipped}}{{spec_link}}
- Sync-with-main: {{sync_summary}}

<!-- last-addressed-comment: 0 -->
```

The trailing HTML comment is the marker `read-pr-comments.sh` reads. After the agent addresses comments and pushes, it updates the marker inline using `gh pr edit <pr> --body "<new-body-with-marker-bumped>"` (read the current body, replace the marker line, write it back — no dedicated script for this). Initial value `0` means "no comments addressed yet" — all comments are unread on first read.

`templates/followup-issue.md`:

```markdown
Filed from work on #{{parent_issue}} ({{pr_url}}).

## Context

{{context}}

## Suggested approach

{{approach}}

## Labels

{{labels}}
```

Substitution is `sed`-based (`s|{{key}}|value|g`). Templates are committed so
formatting changes are reviewable.

### CI watch cadence

Inside `watch-ci.sh`:

- t=0: baseline `gh pr checks <pr> --json ...`.
- `sleep 90` → check (catches lint/frontend failures fast).
- If only backend tests remain pending: `sleep 300` → check (5 min, since they take ~10 min total).
- After that: `sleep 180` → check, then `sleep 120`, then `sleep 60` until either all checks complete or the script's hard cap (25 minutes) trips.
- On any failed check: exit immediately with `FAIL <name>` so the agent gets fast feedback.

The agent makes **one tool call** per watch cycle, not 20-30. While `sleep`
runs, no tokens are spent.

## Decision logic

### Spec-review override

When the lifecycle enters the design step and calls
`superpowers:brainstorming`, the brainstorming skill normally dispatches
its built-in spec-document-reviewer subagent after the spec is written.
Our skill overrides that specific substep: SKILL.md instructs the agent
to dispatch the spec-document-reviewer using the project-local prompt at
`tools/skills/issue-to-merged-pr/spec-document-reviewer-prompt.md`
instead of the plugin's default. The rest of the brainstorming flow
(exploration, design dialogue, spec writing, user-review gate) runs
unmodified, as does `superpowers:writing-plans` afterward.

The local prompt extends the canonical one with three additional review
categories: **contract completeness** (every named mechanism in the spec
is implementable without the planner inventing decisions), **implied-
condition robustness** (every flow holds under conditions the rest of
the spec implies — concurrent invocations, partial failures, state the
spec assumes but doesn't enforce), and **external-constraint conflicts**
(no clash with referenced CLAUDE.md sections, existing tooling, or
platform realities like OS-specific filesystem behavior).

The motivation: the canonical reviewer is calibrated for prose clarity
and approved this spec on first pass; a broader parallel critique
surfaced eight implementation-blocking gaps that fell into those three
categories. The override is project-local, not a fork — the plugin's
files are read-only at their cache path and never touched. Our SKILL.md
owns the spec-review substep and dispatches the reviewer with our prompt
instead of relying on `superpowers:brainstorming`'s default.

### When to skip brainstorm + plan

Skip when:

- Issue label is `chore`, `docs`, `dep-bump`, or `ci-fix`.
- Issue body is < 300 characters AND has no markdown section headers.
- Issue title starts with `fix(<scope>): typo|lint|format|…` (typo-class fixes).

Otherwise, run the full superpowers `brainstorming` → spec →
`writing-plans` → plan flow. The skill records the decision (skipped vs.
ran) in the PR body so reviewers see at a glance.

Default leans **toward** running brainstorm/plan. The skip list is narrow:
overkill costs one extra spec file; under-shooting costs premature
implementation.

### Cross-issue overlap detection

`sync-with-main.sh` emits, on conflict:

```json
{
  "conflicts": ["src/world/combat/views.py", "src/world/scenes/models.py"],
  "conflict_symbols": ["resolve_round", "SceneFactory"],
  "potentially_impacted_issues": [
    {"number": 73, "title": "...", "matched_on": ["src/world/scenes/models.py"]},
    {"number": 81, "title": "...", "matched_on": ["resolve_round"]}
  ]
}
```

Match rule: substring match of (a) conflicted file paths and (b) symbol
names from conflicted diff hunks (function/class/method names extracted
from `git diff --unified=0` hunk headers, e.g. `@@ ... def resolve_round(
...`) against any open issue's body + comments. Cheap; over-inclusive on
purpose. The symbol-name pass catches issues that discuss work
conceptually (`"the resolve_round logic"`) without naming the file. The
agent then decides per-match whether the impact is real, and calls
`comment-on-issue.sh` for real ones. Spurious matches are ignored. The
skill prefers false positives (unnecessary comment) to false negatives
(silent silo across issues).

### When to bail (stop and wait for human)

- **CI check repeat-failure.** The same `(check-name, failure-signature)`
  pair fails 3 times across pushes on this PR. `failure-signature` is the
  name of the first failing test (for test jobs), the first error-prefixed
  line (for lint/build jobs), or the job's first non-zero exit context (for
  others). Reading is from `get-ci-failure.sh`'s output. This distinguishes
  "the same bug, three times" (real bail) from "lint failed three different
  ways" (still iterating).
- **CI thrash cap.** 5 total pushes on this PR across all fix attempts,
  regardless of which check failed. Catches the "fix-one-break-another"
  loop the per-check counter would let slide. Bail comment lists every
  push's check outcomes so the human can see the thrash.
- Both CI bails post a diagnostic comment (what was tried, what failed each
  time, what the agent suspects) and exit.
- Sync-with-main produces conflicts the agent can't auto-resolve confidently
  (e.g. concurrent changes to the same function body, not "different lines
  in same file"). Posts a comment listing the conflict + the impacted issues
  it detected, exits.
- During brainstorm the issue scope appears fundamentally different from
  the title. Agent posts a comment on the original issue suggesting a
  split into sub-issues, exits before opening any PR.
- Any `gh` command fails with auth errors. Means `GH_TOKEN` is missing the
  needed write scopes. Surface clearly so the user can update the PAT.

Each bail-out writes a structured comment containing: what was attempted,
where it stopped, what the human should decide.

## Auth and token

Existing `dev.env` PAT mechanism (introduced on the `devcontainer-gh-access`
work) stays. Scope expands from read-only to:

**Required scopes:**

| Permission | Read | Write |
|---|---|---|
| Metadata | ✓ | — |
| Contents | — | ✓ |
| Pull requests | — | ✓ |
| Issues | — | ✓ |
| Workflows | — | ✓ |
| Actions | ✓ | — |
| Commit Statuses | ✓ | — |
| Dependabot alerts | ✓ | — |

`Workflows: write` is needed because CI fixes occasionally touch
`.github/workflows/*.yml` (e.g., adjusting a job's environment, fixing a
matrix entry). GitHub rejects pushes that modify workflow files without
this scope, even when `Contents: write` is granted.

`Actions: read` + `Commit Statuses: read` together cover what `gh pr checks`
needs: Actions-produced check runs come through the Actions API, and
external-CI commit statuses (plus the legacy Statuses surface) come through
Commit Statuses. GitHub's fine-grained PAT taxonomy no longer has a
single "Checks" category — these two are its modern split.

**Optional scopes (recommended for future-proofing, not required for v1):**

| Permission | Read | Write |
|---|---|---|
| Code Scanning Alerts | ✓ | — |
| Secret Scanning Alerts | ✓ | — |
| Repository Security Advisories | ✓ | — |
| Code Quality | ✓ | — |

Granting these lets the agent read CodeQL findings, leaked-secret reports,
and security advisories when a CI fix or PR comment requires addressing
them. Dependabot already echoes some of this; the explicit scopes give
direct access. The skill's v1 doesn't depend on any of them, so a
maintainer who omits them won't break the workflow — they just get a
clearer "scope missing" message if the agent later tries to read one of
these surfaces.

One token per maintainer, created under each maintainer's own GitHub
identity so commits are correctly attributed. Fine-grained PATs cannot
be scoped to a single repository when the repo is org-owned (per-repo
scoping requires the token owner to own the repo, which isn't the case
for `arxii`). The token is therefore scoped to "all repositories I have
access to" — but the *effective* reach is still bounded by the
maintainer's actual permissions on each repo and by the per-permission
scopes listed in the table above. The skill itself only ever operates
on the repo of the current working directory (`gh` defaults to the repo
the CWD is inside), so a token that *could* reach other org repos is
not directed at them.

`docs/devcontainer-setup.md`'s existing GitHub-access section is updated:

- Title from "GitHub read-only access" → "GitHub access for the issue→PR workflow".
- Scope table updated to the table above.
- One-line note: revoking the token (delete the line in `dev.env` + container
  recreate, or revoke on GitHub for immediate cutoff) takes the autonomous
  workflow offline cleanly.

Branch protection on `main` is the safety net: even with write scopes, the
token cannot bypass branch-protection rules. Direct push to main is rejected;
PRs must merge through GitHub's review path.

## Distribution

`post-create.sh` gains an idempotent symlink loop after the existing
`mise trust` step:

```bash
mkdir -p /home/vscode/.claude/skills
for skill in /workspaces/arxii/tools/skills/*/; do
  name=$(basename "$skill")
  ln -sfn "$skill" "/home/vscode/.claude/skills/$name"
done
```

`-sfn` is idempotent — re-runs cleanly. New skills committed to `tools/skills/`
appear automatically on the next container creation. The paths are
devcontainer-specific (`/workspaces/arxii`, `/home/vscode/.claude`); the
bare-metal equivalent uses `$HOME/.claude/skills` and the repo root, captured
in the README one-liner.

`tools/skills/README.md` is updated:

- Keeps the manual `cp -r` instructions as the **Windows bare-metal**
  fallback (symlinks on Windows require developer mode or an elevated
  shell; `cp -r` works without privileges, at the cost of needing manual
  refresh when skills change).
- Adds the symlink one-liner as the recommended path for macOS / Linux
  bare-metal users.
- Adds a "in the devcontainer this is automatic; for bare-metal, see the
  options below" framing.

The `tools/skills/workflow-friction-audit/` directory is **deleted** as part
of the same commit. Its model (track permission-prompt friction; propose
allowed-tools rules) doesn't apply in the devcontainer where permission
prompts don't fire. A redesigned successor (track failed tool calls,
propose CLAUDE.md edits) is filed as a follow-up issue — the canonical
first work item for the new skill, providing a low-stakes dogfood case.

### Plugin dependency: superpowers

The skill orchestrates `superpowers:brainstorming` and
`superpowers:writing-plans` (see Lifecycle), so the `superpowers` plugin
from the `claude-plugins-official` marketplace must be installed and
enabled in the Claude Code session. Handled in two layers:

**1. Devcontainer install (primary path).** `post-create.sh` runs, after
the symlink loop:

```bash
claude plugin marketplace add anthropics/claude-plugins-official 2>/dev/null || true
claude plugin install superpowers@claude-plugins-official 2>/dev/null || true
```

Both commands are idempotent — already-added marketplace and
already-installed plugin both no-op. `claude plugin install` writes to
`~/.claude/plugins/` (per-user, off-repo) and enables the plugin in
`~/.claude/settings.json`. The 2>/dev/null + `|| true` keeps a
container-creation failure from blocking the whole post-create flow; if
either command genuinely fails, the script-precheck layer catches it on
first skill invocation.

**2. Skill script precheck (defense-in-depth).** `pickup-issue.sh` runs as
its first step:

```bash
if ! claude plugin list 2>/dev/null | grep -q "superpowers@claude-plugins-official"; then
  echo "ERROR: superpowers plugin not installed." >&2
  echo "Install with: claude plugin install superpowers@claude-plugins-official" >&2
  exit 2
fi
```

Catches the bare-metal-without-post-create case, the
container-create-failed case, and the "user disabled superpowers" case.
Fast feedback, clear remediation.

**No `.claude/settings.json` layer.** `.claude/` is gitignored at the
repo root and accumulates per-developer state (hooks, scratch,
worktrees). Carving exceptions to share an `enabledPlugins` declaration
would invite merge churn for negligible benefit, since `claude plugin
install` already handles enabling.

**Bare-metal users.** `tools/skills/issue-to-merged-pr/README.md`
includes a "Setup" section with the install one-liner above. The
precheck's error message points users at the install command without
requiring docs.

## Invocation

`SKILL.md`'s `description:` frontmatter is what activates the skill from a
user message. Proposed text:

> `description: Use when working on a GitHub issue from start to merged PR. Picks up an issue (or prompts for one), runs brainstorm/spec/plan, implements, opens a PR, watches CI and fixes failures, and handles post-merge cleanup including filing follow-up issues.`

That fires on "work on issue 47", "pick up #47", "open a PR for the
friction-skill rework", etc.

`CLAUDE.md`'s Git Workflow section gets a one-line cross-reference pointing
at the skill, and its existing "**No GitHub CLI:** Do not use `gh` commands"
rule is scoped: the prohibition applies to ad-hoc agent usage; the
`issue-to-merged-pr` skill's scripts are the sanctioned `gh` consumer (token
auth + branch protection + audited script contracts make it safe in a way
ad-hoc `gh` calls are not). The plan should land both edits in the same PR
that introduces the skill.

## Validation

1. **`shellcheck` clean**. Every script in `scripts/` passes `shellcheck`.
   Pre-commit can grow a `shellcheck` hook for `tools/skills/**/*.sh`.
2. **`--dry-run`** on state-mutating scripts. Lets you exercise the
   end-to-end workflow against a real issue without touching the issue
   board.
3. **No unit tests for `SKILL.md`** — a markdown recipe isn't testable
   in the usual sense.
4. **Branch protection on main** = safety net of last resort.

### Dogfood test

The first real validation is running the new skill on the friction-skill
rework follow-up issue (filed at PR-open time of THIS skill's
implementation):

1. The current branch's PR merges → skill is installed via symlink on
   container recreate.
2. User runs `claude` inside the container, says "work on issue #N" (the
   friction-skill rework).
3. Walk the lifecycle. User stays in the loop for brainstorm/plan
   approvals (existing superpowers gates) and PR review on GitHub.
4. Verify:
   - Branch named per convention (`feature-N-rework-friction-skill` or similar).
   - Spec in `docs/superpowers/specs/`, plan in `docs/superpowers/plans/`.
   - PR body has `Closes #N` and the documented sections.
   - Sync-with-main fires at least once.
   - CI watch loop respects the cadence (no token-burning spam).
   - Post-merge cleanup runs after merge on GitHub.
   - Any deferred follow-up issues land on the board, linked from the PR.

Failure modes from that run get fixed via the workflow itself (recursive
validation). Long-term: if `gh`'s output format or GitHub's PR shape
changes, things will break silently — mitigated by human-in-the-loop PR
review early on. Real integration tests can come later if the skill
stabilizes.

## Non-goals (explicit)

- **Persistent workflow state on disk.** GitHub holds the truth (PR state,
  comment timestamps, check status). The skill reads it on every
  invocation. No `.workflow-state.json` to maintain.
- **Auto-merge.** The skill never merges the PR. Merge is always a human
  action on GitHub.
- **Cross-repo work.** The skill operates on the repo of the current
  working directory only. Issues/PRs in other repos are out of scope by
  design, even when the maintainer's PAT technically has access to them
  (fine-grained PATs can't be scoped per-repo for org-owned repos like
  `arxii`, so the boundary is enforced by the skill's behavior, not by
  the token).
- **Replacing superpowers' brainstorming and writing-plans skills.** This
  skill orchestrates them; it does not duplicate their logic.
- **Automated regression tests.** The skill is validated by dogfood
  initially. Real tests are a follow-up if it stabilizes.

## Open questions deferred to implementation

- Exact `gh` JSON field names — verify against current `gh` version during
  implementation.
- Whether `gh pr checks` reports "in progress" distinguishably from
  "queued" — relevant to the cadence; check empirically.
- Whether the `--force-with-lease` flow needs any special handling when the
  remote tracking ref has moved between rebase and push.
- Authorship: each maintainer's PAT carries their identity, so commits
  attribute correctly. Verify the Co-Authored-By line in commits is still
  desired.

## Related work / context

- `devcontainer-gh-access` and `b1ee238a`: prior commits establishing the
  PAT + `gh` install + env-file mechanism this skill builds on.
- `tools/skills/workflow-friction-audit/`: deleted as part of this work
  (see Distribution section).
- `docs/devcontainer-setup.md`: updated as part of this work to reflect
  expanded token scopes.
