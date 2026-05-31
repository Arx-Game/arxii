---
description: Use when working on a GitHub issue from start to merged PR. Picks up an issue (or prompts for one), drafts the spec onto the issue for team review, implements after a member approves it (spec:approved label), opens a PR, watches CI and fixes failures, and handles post-merge cleanup including filing follow-up issues.
---

# issue-to-merged-pr

This skill carries a GitHub issue from pickup through to a merged PR. It is
**multi-invocation**: the agent works up to a human gate, then exits while
review is async. There are **two** such gates — **spec review on the issue**
(a member applies the `spec:approved` label) and **code review on the PR** —
plus CI. The user re-invokes the skill in a new session; the agent reads the
issue + PR state and picks up the right phase.
**No persistent on-disk workflow state — GitHub (labels + issue body + PR)
holds the truth. New specs live in the issue body rather than as committed
`docs/superpowers/` files.**

The full design is in `tools/skills/issue-to-merged-pr/references/design.md`.
This file is the executable recipe.

## Required plugin

This skill orchestrates `superpowers:brainstorming` and
`superpowers:writing-plans`. The `pickup-issue.sh` script checks for the
plugin's presence and fails fast (`exit 2`) with the install commands if
missing. In the devcontainer, `post-create.sh` installs it automatically.

**On re-invocation** (any phase other than initial Pickup), the agent
should run the same precheck before invoking any `superpowers:*` skill,
since re-invocations skip `pickup-issue.sh`. One-liner:

```bash
claude plugin list 2>/dev/null | grep -q "superpowers@claude-plugins-official" || {
  echo "Install: claude plugin marketplace add anthropics/claude-plugins-official && claude plugin install superpowers@claude-plugins-official" >&2
  exit 2
}
```

In phases that don't touch `superpowers:*` (CI watch, CI fix, post-merge
cleanup), the precheck is optional — those phases only need `gh`, `git`,
and `jq`, all of which are devcontainer baseline.

## Phase detection on re-invocation

Detection is two-stage: first the **issue/label state** (pre-PR phases), then —
only once a PR exists — the **PR state** table further down.

### Pre-PR phases (driven by issue labels — the spec lives on the issue)

```bash
gh issue view <N> --json state,labels,body
```

Read the `status:*` and `spec:approved` labels. First match wins:

| labels on the issue | Phase |
|---|---|
| `spec:approved` present, no open PR yet | **Implementation** — flip `status:spec-review`→`status:implementing`, then build |
| `status:spec-review`, no `spec:approved` | **Await-approval** — spec is on the issue; a member must apply `spec:approved`. Exit (review is on the human). |
| `status:spec-draft` (or no `<!-- spec:start -->` marker in the body) | **Design** — draft the spec into the issue body |
| no `status:*` label | **Pickup** (fresh) |

**The agent MUST NEVER apply `spec:approved` itself.** Only a human org member
applies it — GitHub restricts label-writes to Triage+, so outsiders can't, but
the agent holds the maintainer PAT and so must self-restrain. The agent only
polls for the label.

Once an open PR exists for the branch, use the PR-state table below instead.

When invoked with no arg, or with a PR number / issue number whose branch
already has an open PR, run:

```bash
gh pr view <pr-or-branch> --json state,mergedAt,statusCheckRollup,reviewDecision,mergeStateStatus
```

(`gh pr view`'s JSON taxonomy is camelCase and has no boolean `merged`
field; `state == "MERGED"` is the definitive merge indicator, and
`mergedAt` is the timestamp.)

For each entry in `statusCheckRollup`, the relevant fields are `status`
(`QUEUED` / `IN_PROGRESS` / `COMPLETED`) and `conclusion` (`SUCCESS` /
`FAILURE` / `CANCELLED` / `TIMED_OUT` / `SKIPPED` / `NEUTRAL` / etc.).
A check is "failing" when `status == COMPLETED && conclusion` is one of
`FAILURE`, `CANCELLED`, `TIMED_OUT`, `ACTION_REQUIRED`. Pending = any
`status != COMPLETED`.

Then, only if checks are all-success and the PR is open, call
`scripts/read-pr-comments.sh <pr>` to populate the unread-comments cell.
Pick the phase from this table (rows top-to-bottom; first match wins):

| `state` | `mergeStateStatus` | `statusCheckRollup` aggregate | unread-comments | Phase |
|---|---|---|---|---|
| `MERGED` | — | — | — | **Post-merge cleanup** |
| `CLOSED` | — | — | — | **Closed-without-merge** (notify user, exit) |
| `OPEN` | `DIRTY` / `BEHIND` | — | — | **Conflict-during-review** (re-sync, push) |
| `OPEN` | `BLOCKED` | all success | none | **Blocked-on-review** (post comment noting required reviewers missing, exit) |
| `OPEN` | — | any failure | — | **CI fix** (read failures, fix, push, return to CI watch) |
| `OPEN` | — | any pending | — | **CI watch** (resume `watch-ci.sh`) |
| `OPEN` | — | all success | exist | **PR-comment** (address comments, push, bump marker) |
| `OPEN` | — | all success | none | **Idle** (post status comment, exit — review is on human) |

If the branch exists but has no open PR, fall back to the **Pre-PR phases**
table above (driven by the issue's labels) to decide between Design,
Await-approval, and Implementation.

## Lifecycle

### 1. Pickup

- If invoked without an issue number, ask the user. If they describe work
  that doesn't have an issue yet, file one with `scripts/file-followup.sh`
  first and use its number.
- Run `scripts/pickup-issue.sh <N>`. It checks the superpowers plugin,
  fetches the issue, infers type, ensures the lane labels exist, claims the
  issue (assign + `status:spec-draft`), creates the branch, and emits JSON.
- **Model selection.** Read the `model` and `complexity` fields from the
  emitted JSON. If `model` is non-empty, switch now — before any design,
  planning, or implementation work:
  - `complexity:high` → `claude-opus-4-8` — run `/model claude-opus-4-8`
  - `complexity:medium` → `claude-sonnet-4-6` — run `/model claude-sonnet-4-6`
  - `complexity:low` → `claude-sonnet-4-6` as the session model; use
    `opts.model: "claude-haiku-4-5-20251001"` for leaf subagents in workflow
    scripts where appropriate.
  - No `complexity:*` label → no change; proceed on the current model.
  In workflow scripts (`agent()` calls), set `opts.model` consistently with
  the above mapping so subagents inherit the right tier.

### 2. Design (skipped for trivial issue types)

Skip the design step when:
- Issue label is `chore`, `docs`, `dep-bump`, or `ci-fix`.
- Issue body is < 300 characters AND has no markdown section headers.
- Issue title starts with `fix(<scope>): typo|lint|format|…`.

When skipping, go straight to Implementation (claim `status:implementing`).

Otherwise, claim the draft lane (`status:spec-draft`; pickup sets this) and
invoke `superpowers:brainstorming`. **Override two superpowers substeps:**

- **Spec destination:** write the spec into the **issue body**, between
  `<!-- spec:start -->` and `<!-- spec:end -->` markers, preserving the original
  problem statement above them (`gh issue edit <N> --body-file`). Don't create a
  new committed `docs/superpowers/` spec file for this work.
- **Spec-review dispatch:** when the brainstorming flow reaches "dispatch
  spec-document-reviewer," dispatch with the prompt at
  `tools/skills/issue-to-merged-pr/spec-document-reviewer-prompt.md` instead of
  superpowers' default.

**MANDATORY before posting the spec: run the `verify-against-code` pass**
(skill at `tools/skills/verify-against-code/`). For every new surface the design
proposes, verify against code (not docs/summaries) and label it
`[BUILT & WIRED]` / `[BUILT, NOT WIRED]` / `[ABSENT]` with file:line + caller
evidence; treat INDEX/MODEL_MAP/architecture docs as possibly-stale hints and
correct any stale doc at its source. **Embed the resulting anti-reinvention
ledger as a section of the spec in the issue body.** A spec without a
code-verified ledger is not finalized. (This codifies CLAUDE.md's
"Anti-Reinvention Pass" into the workflow.)

Then hand off for **spec review** and exit:

1. `gh issue edit <N> --remove-label status:spec-draft --add-label status:spec-review`.
2. Post a comment that @-mentions the review target (default `@TehomCD`;
   configurable to a `@Arx-Game/<team>` handle) and links the spec section.
3. **Exit.** Spec review is async and on a human. Do NOT proceed to plan or
   implementation, and **do NOT apply `spec:approved`** — only a member does.

The agent resumes (in a later invocation) once a member has applied
`spec:approved`; the plan from `superpowers:writing-plans` is produced then and
is **ephemeral** (worktree-only, never committed).

Record the decision (ran vs. skipped) — it goes in the PR body's Notes
section.

### 3. Implementation

Entry condition: the issue carries `spec:approved` (a member approved the spec
on the issue). On entry, flip the lane:
`gh issue edit <N> --remove-label status:spec-review --add-label status:implementing`.
Create the worktree (`superpowers:using-git-worktrees`), then invoke
`superpowers:writing-plans` to produce the **ephemeral** plan (worktree-only,
never committed).

When `superpowers:writing-plans` reaches its execution-handoff (the
"Subagent-Driven vs. Inline? Which approach?" prompt), **do NOT prompt — go
straight to `superpowers:subagent-driven-development`.** Subagent-driven is the
standing default for this project; the execution-mode selection is not a
decision the user wants to make. (Inline execution is only for when subagents
are unavailable.)

Follow the plan if one exists; otherwise implement directly. Commit
frequently. The plan's spec-review-loop applies to brainstorming runs; for
skipped-design tasks, just edit and commit.

### 4. Sync with main

Run `scripts/sync-with-main.sh <branch>`. The script automatically picks the
right strategy:
- **Branch not yet on origin (local-only):** rebase onto origin/main. Clean
  linear history.
- **Branch already on origin (pushed):** merge origin/main in. Avoids
  rewriting already-published history, so the next `git push` is a fast-
  forward — no force-push (and no user approval prompt for it).

The choice is recorded in the JSON's `strategy` field on conflict.

On conflict (exit 4):
- Read the emitted JSON.
- For each entry in `potentially_impacted_issues` where the impact is
  judged real, call `scripts/comment-on-issue.sh <issue> <body-file>` to
  notify the other issue's stakeholders.
- Resolve the conflicts, then continue the in-progress sync
  (`git rebase --continue` or `git merge --continue` depending on
  `strategy`).

### 5. Push & open PR

Compose the PR body's substitution values (summary, follow-ups, sync
summary). For each deferred follow-up identified during implementation,
call `scripts/file-followup.sh <title> <body-path> <labels...>` NOW (before
opening the PR) and collect the issue numbers. Then:

```bash
PR_SUMMARY="..." PR_RAN_OR_SKIPPED="ran" PR_SYNC_SUMMARY="..." \
  scripts/open-pr.sh <branch> <issue-N> <followup-1> <followup-2> ...
```

The PR body references the approved spec via `Closes #<issue>` — the spec lives
in the issue body, so there is no spec-file link to pass.

### 6. CI watch

> ⚠️ **NEVER use Opus for CI watch or any looping/polling phase.** The watch
> loop runs up to 25 minutes at 60-second intervals — potentially 25+ model
> calls for pure polling work. If you switched to Opus at pickup, switch back
> to Sonnet (`/model claude-sonnet-4-6`) before running `watch-ci.sh`. Opus
> is for design and implementation, not waiting.

Run `scripts/watch-ci.sh <pr-N>`. Outcomes:
- `OK` (exit 0): post a brief status comment, exit the session.
- `FAIL <check-name>` (exit 5): enter the CI-fix phase.
- timeout (exit 6): post a diagnostic, exit.

### 7. CI fix

Run `scripts/get-ci-failure.sh <pr-N> <check-name>`. Read the log, fix the
issue, commit, push, return to CI watch.

**Bail conditions:**
- **Repeat failure:** same `(check-name, failure-signature)` pair fails 3
  times across pushes. `failure-signature` is the first failing test name
  (test jobs), the first error-prefixed line (lint/build jobs), or the
  job's first non-zero exit context (others).
- **Thrash cap:** 5 total pushes on this PR across all fix attempts.

**Cross-session attempt counting.** Since the skill has no on-disk state,
the count is reconstructed from the PR's own commits + the agent's prior
attempt-trail comments. Each CI-fix attempt the agent makes, post a PR
comment with this exact prefix:

> `<!-- ci-fix-attempt --> check: <name>, signature: <signature>, push: <commit-sha-short>`

On every re-invocation that enters CI-fix, read prior comments via
`scripts/read-pr-comments.sh`, count entries matching the marker prefix,
and apply the bail thresholds against the historical total. Without this
trail, multi-session thrash is undetectable.

On either bail, post a diagnostic PR comment summarizing every attempt
(with the same marker for future reconstructability) and exit.

### 8. PR-comment phase (re-invocation after human review)

When phase detection lands on **PR-comment**:
- Run `scripts/read-pr-comments.sh <pr-N>` — get unread comments as JSON.
- Address each: edit code, commit.
- Push.
- **Takeaway evaluation** (see below — runs before the marker bump).
- Update the PR body marker:

```bash
NEW_MAX=<max comment id you addressed>
BODY=$(gh pr view <pr> --json body --jq .body)
# -E (ERE) so [0-9]+ works on both GNU sed (Linux) and BSD sed (macOS).
NEW_BODY=$(sed -E "s/<!-- last-addressed-comment: [0-9]+ -->/<!-- last-addressed-comment: $NEW_MAX -->/" <<<"$BODY")
printf '%s' "$NEW_BODY" | gh pr edit <pr> --body-file -
```

#### Takeaway evaluation

After all actionable comments are committed (above) and **before** bumping the marker, evaluate each addressed comment for a non-obvious takeaway worth posting on a related issue.

**Criteria for "takeaway worth posting":**
- The comment surfaced a gotcha, workflow weakness, or design decision that future agents working on a related, currently-open (or recently-closed, <90d) issue would benefit from.
- The insight is not about THIS PR's work — PR-local insights go in the PR description or commit message, never a sibling-issue comment.

**Ordering rules — follow in this order:**
1. **Default disposition: actionable.** For every review comment, first ask "can this be addressed in this PR?" Treat as actionable unless clearly out-of-scope (separable concern, different system, or reviewer framed it as future work).
2. Address all actionable comments in code FIRST. Takeaway evaluation runs only after.
3. A single comment can yield both a code change AND a takeaway — not mutually exclusive.
4. When uncertain whether a comment is in-scope or future work, **address it now**. Tie-breaker.

**Posting:** post unilaterally (no user confirmation; the criteria above set the bar). Format:

```
> **Takeaway from PR #<N>:** <one-sentence headline>
>
> <2-4 sentences of specific insight>
>
> Refs: PR #<N>, related: #<other-issues-if-any>
```

Run the **Layer 3 secret-scan** before posting (cross-references `tools/skills/workflow-friction-audit/`):

```bash
TAKEAWAY_TMP=$(mktemp)
# Write the comment body to "$TAKEAWAY_TMP" via the Write tool or a heredoc.

USER_PATTERNS=tools/skills/workflow-friction-audit/secret-patterns.txt
if [ -f "$USER_PATTERNS" ]; then
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt -f "$USER_PATTERNS" "$TAKEAWAY_TMP"
else
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt "$TAKEAWAY_TMP"
fi
```

- **Exit 0** (secret match): abort the post, surface the offending line to the user, exit (see "When to bail"). Do NOT call `comment-on-issue.sh`.
- **Exit 1** (clean): proceed —

```bash
bash tools/skills/issue-to-merged-pr/scripts/comment-on-issue.sh <target-issue-N> "$TAKEAWAY_TMP"
```

Then continue to the marker bump.

Return to CI watch.

### 9. Post-merge cleanup

Run `scripts/post-merge-cleanup.sh <branch> <pr-N>`. Read the JSON:
- For any `linked_issue_actions` entry with `action: "needs-attention"`,
  post a comment on that issue explaining what merged.
- For review-driven follow-ups identified during the PR-comment phase,
  file them now with `scripts/file-followup.sh`.

#### Takeaway evaluation (post-merge)

Review the merged work for any non-obvious takeaway worth posting on:
- Issues in `linked_issue_actions` (especially `needs-attention` entries).
- Deferred follow-ups Claude filed during the PR's lifecycle.

Apply the same criteria, ordering rules, format, and Layer 3 secret-scan as Step 8's takeaway evaluation. Post unilaterally if criteria are met. Use `scripts/comment-on-issue.sh` for the post.

## When to bail (stop and wait for human)

- CI repeat-failure or thrash cap (see above).
- Sync conflicts the agent can't auto-resolve confidently.
- During brainstorm, scope feels fundamentally different from the title —
  post on the original issue suggesting a split, exit before opening any PR.
- Any `gh` command fails with auth errors. Surface the error and the
  `gh auth status` output; the user needs to update their PAT.
- A takeaway-capture post would contain a secret-pattern match (Layer 3
  gate from `tools/skills/workflow-friction-audit/`). Abort the post,
  surface the offending line to the user, exit without commenting.

Each bail writes a structured PR or issue comment with: what was attempted,
where it stopped, what the human should decide.

## Quick reference

| Need | Script |
|---|---|
| Start work on issue N | `scripts/pickup-issue.sh N` |
| Sync with main mid-work | `scripts/sync-with-main.sh <branch>` |
| Open the PR | `scripts/open-pr.sh <branch> <issue> [followups...]` |
| File a follow-up issue | `scripts/file-followup.sh <title> <body-path> [labels...]` |
| Comment on an issue | `scripts/comment-on-issue.sh <issue> <body-path>` |
| Watch CI | `scripts/watch-ci.sh <pr>` |
| Read failing log | `scripts/get-ci-failure.sh <pr> <check-name>` |
| Read unread PR comments | `scripts/read-pr-comments.sh <pr>` |
| Clean up after merge | `scripts/post-merge-cleanup.sh <branch> <pr>` |

All state-mutating scripts support `--dry-run`.
