---
name: issue-to-merged-pr
description: "Use when working on a GitHub issue from start to merged PR. Picks up an issue (or prompts for one), drafts the spec onto the issue body for team review, implements after a member approves it (spec:approved label), opens a PR, watches CI and fixes failures, and handles post-merge cleanup including filing follow-up issues. Polytoken-native: orchestrates the ported brainstorming + writing-plans + using-git-worktrees skills."
compatibility: polytoken-only
---

# shared-assets-from: issue-to-merged-pr

# issue-to-merged-pr (Polytoken)

This skill carries a GitHub issue from pickup through to a merged PR. It is
**multi-invocation**: the agent works up to a human gate, then exits while review
is async. There are **two** such gates — **spec review on the issue** (a member
applies the `spec:approved` label) and **code review on the PR** — plus CI. The
user re-invokes the skill in a new session; the agent reads the issue + PR state
and picks up the right phase.

**No persistent on-disk workflow state — GitHub (labels + issue body + PR) holds
the truth. Specs live in the issue body between `<!-- spec:start -->` and
`<!-- spec:end -->` markers, never as committed files.**

This is the **Polytoken-native** counterpart of the Claude-Code-only
`issue-to-merged-pr` skill. It reuses the **same bash scripts** verbatim
(`tools/skills/issue-to-merged-pr/scripts/*`) but orchestrates the ported
harness-agnostic skills (`brainstorming`, `writing-plans`, `using-git-worktrees`
under `tools/skills/`) instead of the `superpowers` Claude Code plugin.

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

### PR phases (driven by PR state)

When invoked with no arg, or with a PR number / issue number whose branch
already has an open PR, run:

```bash
gh pr view <pr-or-branch> --json state,mergedAt,statusCheckRollup,reviewDecision,mergeStateStatus
```

Then, only if checks are all-success and the PR is open, call
`scripts/read-pr-comments.sh <pr>` to populate the unread-comments cell. Pick the
phase from this table (rows top-to-bottom; first match wins):

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
table above.

## Lifecycle

### 1. Pickup

- If invoked without an issue number, ask the user. If they describe work that
  doesn't have an issue yet, file one with `scripts/file-followup.sh` first and
  use its number.
- Run `scripts/pickup-issue.sh <N>`. It checks skill availability (superpowers
  plugin OR ported skills — either passes), fetches the issue, infers type,
  ensures the lane labels exist, claims the issue (assign + `status:spec-draft`),
  creates the branch, and emits JSON.
- **Model selection.** Read the `model` and `complexity` fields from the emitted
  JSON. `pickup-issue.sh` derives the model from the `complexity:*` label, with
  tier names overridable via `ISSUE_MODEL_HIGH` / `ISSUE_MODEL_MEDIUM` /
  `ISSUE_MODEL_LOW` env vars (defaults are Claude Code tiers; set them to
  umans-* models for Polytoken). If `model` is non-empty and the harness supports
  a model switch, switch now — before any design, planning, or implementation.

### 2. Design (skipped for trivial issue types)

Skip the design step when:
- Issue label is `chore`, `docs`, `dep-bump`, or `ci-fix`.
- Issue body is < 300 characters AND has no markdown section headers.
- Issue title starts with `fix(<scope>): typo|lint|format|…`.

When skipping, go straight to Implementation (claim `status:implementing`).

Otherwise, claim the draft lane (`status:spec-draft`; pickup sets this) and
invoke the **ported `brainstorming` skill** (`tools/skills/brainstorming/`). It
handles the full design dialogue and writes the spec into the issue body. Two
points it already bakes in (from the port):
- **Spec destination:** the issue body, between `<!-- spec:start -->` and
  `<!-- spec:end -->` markers (`gh issue edit <N> --body-file`), using
  `docs/spec-template.md`'s section layout. No committed spec file.
- **Mandatory `verify-against-code` pass:** before the spec is finalized, run
  `tools/skills/verify-against-code/` and embed the anti-reinvention ledger as a
  section of the spec.
- **Spec-review dispatch:** when the brainstorming skill reaches spec review,
  dispatch with the prompt at
  `tools/skills/issue-to-merged-pr/spec-document-reviewer-prompt.md`.

Then hand off for **spec review** and exit (the brainstorming skill's final
step):
1. `gh issue edit <N> --remove-label status:spec-draft --add-label status:spec-review`.
2. Post a comment that @-mentions the review target (default `@TehomCD`;
   configurable to a `@Arx-Game/<team>` handle) and links the spec section.
3. **Exit.** Spec review is async and on a human. Do NOT proceed to plan or
   implementation, and **do NOT apply `spec:approved`**.

The agent resumes (in a later invocation) once a member has applied
`spec:approved`; the plan from the ported `writing-plans` skill is produced then
and is **ephemeral** (worktree-only, never committed).

Record the decision (ran vs. skipped) — it goes in the PR body's Notes section.

### 3. Implementation

Entry condition: the issue carries `spec:approved` (a member approved the spec on
the issue). On entry, flip the lane:
`gh issue edit <N> --remove-label status:spec-review --add-label status:implementing`.
Create the worktree via the ported **`using-git-worktrees`** skill
(`tools/skills/using-git-worktrees/`), then invoke the ported **`writing-plans`**
skill (`tools/skills/writing-plans/`) to produce the **ephemeral** plan
(worktree-only, never committed).

The ported `writing-plans` skill goes straight to implementation (it does not
prompt subagent-vs-inline). Work through the plan task-by-task in this session,
committing after each. Follow the plan if one exists; otherwise implement
directly.

**Keep docs in tandem.** Before opening the PR, update the docs your change
affects *in the same PR* — system doc + `docs/systems/INDEX.md`,
`docs/systems/MODEL_MAP.md` (regen after model/signature changes), the relevant
`docs/architecture/*.md` and its diagrams, and the roadmap. A code change that
leaves its docs stale is incomplete.

### 4. Sync with main

Sync **once here** to surface conflicts and migration collisions early. You do
**not** need to re-sync every time main moves afterward — the merge queue
re-integrates the PR against the latest main at merge time.

Run `scripts/sync-with-main.sh <branch>`. On conflict (exit 4): read the emitted
JSON, comment on impacted issues via `scripts/comment-on-issue.sh`, resolve the
conflicts, then continue (`git rebase --continue` / `git merge --continue`).

### 5. Push & open PR

Compose the PR body's substitution values. For each deferred follow-up, call
`scripts/file-followup.sh <title> <body-path> <labels...>` NOW (before opening
the PR) and collect the issue numbers. **Before filing each follow-up, run the
`verify-against-code` pass on its premise** — drop it if already built; file
design-open items as `needs-design` questions, not asserted work.

```bash
PR_SUMMARY="..." PR_RAN_OR_SKIPPED="ran" PR_SYNC_SUMMARY="..." \
  scripts/open-pr.sh <branch> <issue-N> <followup-1> <followup-2> ...
```

The PR body references the approved spec via `Closes #<issue>`.

**Before pushing, run `uv run pre-commit run --all-files`** — matches CI's
`pre-commit` job exactly (committing with hooks only checks changed files).

### 6. CI watch

Run `scripts/watch-ci.sh <pr-N>`. Outcomes:
- `OK` (exit 0): enqueue for the merge queue with `scripts/enqueue-pr.sh <pr-N>`,
  post a brief status comment, exit the session. **Do NOT re-sync or merge by
  hand** — the merge queue re-tests and merges once a human approves.
- `FAIL <check-name>` (exit 5): enter the CI-fix phase.
- timeout (exit 6): post a diagnostic, exit.

### 7. CI fix

Run `scripts/get-ci-failure.sh <pr-N> <check-name>`. Read the log, fix the issue,
commit, push, return to CI watch.

**Bail conditions:**
- **Repeat failure:** same `(check-name, failure-signature)` pair fails 3 times
  across pushes.
- **Thrash cap:** 5 total pushes on this PR across all fix attempts.

Cross-session attempt counting reconstructs the count from the PR's own commits +
prior attempt-trail comments. Each CI-fix attempt posts a PR comment with this
exact prefix:

> `<!-- ci-fix-attempt --> check: <name>, signature: <signature>, push: <commit-sha-short>`

On either bail, post a diagnostic PR comment summarizing every attempt and exit.

### 8. PR-comment phase (re-invocation after human review)

When phase detection lands on **PR-comment**:
- Run `scripts/read-pr-comments.sh <pr-N>` — get unread comments as JSON.
- Address each: edit code, commit.
- Push.
- **Takeaway evaluation** (see below — runs before the marker bump).
- Update the PR body marker via the REST API (not `gh pr edit`, which errors on
  the deprecated Projects field):

```bash
NEW_MAX=<max comment id you addressed>
BODY=$(gh pr view <pr> --json body --jq .body)
NEW_BODY=$(sed -E "s/<!-- last-addressed-comment: [0-9]+ -->/<!-- last-addressed-comment: $NEW_MAX -->/" <<<"$BODY")
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
printf '%s' "$NEW_BODY" | gh api -X PATCH "repos/$REPO/pulls/<pr>" -F body=@-
```

#### Takeaway evaluation

After all actionable comments are committed and before bumping the marker,
evaluate each addressed comment for a non-obvious takeaway worth posting on a
related issue. Post unilaterally if the criteria are met (see the Claude Code
sibling skill for the full criteria/format). Run the **Layer 3 secret-scan**
before posting (cross-references `tools/skills/workflow-friction-audit/`):

```bash
TAKEAWAY_TMP=$(mktemp)
# Write the comment body to "$TAKEAWAY_TMP".
if [ -f tools/skills/workflow-friction-audit/secret-patterns.txt ]; then
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt -f tools/skills/workflow-friction-audit/secret-patterns.txt "$TAKEAWAY_TMP"
else
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt "$TAKEAWAY_TMP"
fi
# Exit 0 (secret match): abort the post, surface the line, exit.
# Exit 1 (clean): proceed to comment-on-issue.sh.
bash tools/skills/issue-to-merged-pr/scripts/comment-on-issue.sh <target-issue-N> "$TAKEAWAY_TMP"
```

Return to CI watch.

### 9. Post-merge cleanup

Run `scripts/post-merge-cleanup.sh <branch> <pr-N>`. Read the JSON:
- For any `linked_issue_actions` entry with `action: "needs-attention"`, post a
  comment on that issue explaining what merged.
- For review-driven follow-ups identified during the PR-comment phase, file them
  now with `scripts/file-followup.sh`.

Apply the same takeaway evaluation, criteria, format, and Layer 3 secret-scan
as Step 8's.

## When to bail (stop and wait for human)

- CI repeat-failure or thrash cap.
- Sync conflicts the agent can't auto-resolve confidently.
- During brainstorm, scope feels fundamentally different from the title — post
  on the original issue suggesting a split, exit before opening any PR.
- Any `gh` command fails with auth errors. Surface the error and `gh auth
  status` output.
- A takeaway-capture post would contain a secret-pattern match. Abort the post,
  surface the offending line, exit without commenting.

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
| Enqueue for the merge queue | `scripts/enqueue-pr.sh <pr>` |
| Read failing log | `scripts/get-ci-failure.sh <pr> <check-name>` |
| Read unread PR comments | `scripts/read-pr-comments.sh <pr>` |
| Clean up after merge | `scripts/post-merge-cleanup.sh <branch> <pr>` |

All state-mutating scripts support `--dry-run`. Scripts are at
`tools/skills/issue-to-merged-pr/scripts/` (shared with the Claude Code sibling
skill).
