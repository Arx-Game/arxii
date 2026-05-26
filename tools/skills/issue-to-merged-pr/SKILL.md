---
description: Use when working on a GitHub issue from start to merged PR. Picks up an issue (or prompts for one), runs brainstorm/spec/plan, implements, opens a PR, watches CI and fixes failures, and handles post-merge cleanup including filing follow-up issues.
---

# issue-to-merged-pr

This skill carries a GitHub issue from pickup through to a merged PR. It is
**multi-invocation**: a single session typically does Pickup → Push, then
exits while CI runs and human review is async. The user re-invokes the skill
in a new session; the agent reads PR state and picks up the right phase.
**No persistent on-disk workflow state — GitHub holds the truth.**

The full design is in
`docs/superpowers/specs/2026-05-25-issue-to-merged-pr-design.md`. This file
is the executable recipe.

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

If the branch matches the convention `<type>-<N>-<slug>` but has no open PR,
the agent is mid-implementation and resumes from the Implementation step.

## Lifecycle

### 1. Pickup

- If invoked without an issue number, ask the user. If they describe work
  that doesn't have an issue yet, file one with `scripts/file-followup.sh`
  first and use its number.
- Run `scripts/pickup-issue.sh <N>`. It checks the superpowers plugin,
  fetches the issue, infers type, creates the branch, and emits JSON.

### 2. Design (skipped for trivial issue types)

Skip the design step when:
- Issue label is `chore`, `docs`, `dep-bump`, or `ci-fix`.
- Issue body is < 300 characters AND has no markdown section headers.
- Issue title starts with `fix(<scope>): typo|lint|format|…`.

Otherwise: invoke `superpowers:brainstorming`. **Override the spec-review
substep**: when the brainstorming flow reaches "dispatch spec-document-
reviewer," dispatch the reviewer with the prompt at
`tools/skills/issue-to-merged-pr/spec-document-reviewer-prompt.md` instead
of superpowers' default. After the spec is approved and committed, invoke
`superpowers:writing-plans` for the plan.

Record the decision (ran vs. skipped) — it goes in the PR body's Notes
section.

### 3. Implementation

Follow the plan if one exists; otherwise implement directly. Commit
frequently. The plan's spec-review-loop applies to brainstorming runs; for
skipped-design tasks, just edit and commit.

### 4. Sync with main

Run `scripts/sync-with-main.sh <branch>`. On conflict (exit 4):
- Read the emitted JSON.
- For each entry in `potentially_impacted_issues` where the impact is
  judged real, call `scripts/comment-on-issue.sh <issue> <body-file>` to
  notify the other issue's stakeholders.
- Resolve the conflicts, continue the rebase.

### 5. Push & open PR

Compose the PR body's substitution values (summary, follow-ups, sync
summary). For each deferred follow-up identified during implementation,
call `scripts/file-followup.sh <title> <body-path> <labels...>` NOW (before
opening the PR) and collect the issue numbers. Then:

```bash
PR_SUMMARY="..." PR_RAN_OR_SKIPPED="ran" PR_SPEC_LINK="docs/superpowers/specs/<file>.md" PR_SYNC_SUMMARY="..." \
  scripts/open-pr.sh <branch> <issue-N> <followup-1> <followup-2> ...
```

### 6. CI watch

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
- Update the PR body marker:

```bash
NEW_MAX=<max comment id you addressed>
BODY=$(gh pr view <pr> --json body --jq .body)
# -E (ERE) so [0-9]+ works on both GNU sed (Linux) and BSD sed (macOS).
NEW_BODY=$(sed -E "s/<!-- last-addressed-comment: [0-9]+ -->/<!-- last-addressed-comment: $NEW_MAX -->/" <<<"$BODY")
printf '%s' "$NEW_BODY" | gh pr edit <pr> --body-file -
```

Return to CI watch.

### 9. Post-merge cleanup

Run `scripts/post-merge-cleanup.sh <branch> <pr-N>`. Read the JSON:
- For any `linked_issue_actions` entry with `action: "needs-attention"`,
  post a comment on that issue explaining what merged.
- For review-driven follow-ups identified during the PR-comment phase,
  file them now with `scripts/file-followup.sh`.

## When to bail (stop and wait for human)

- CI repeat-failure or thrash cap (see above).
- Sync conflicts the agent can't auto-resolve confidently.
- During brainstorm, scope feels fundamentally different from the title —
  post on the original issue suggesting a split, exit before opening any PR.
- Any `gh` command fails with auth errors. Surface the error and the
  `gh auth status` output; the user needs to update their PAT.

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
