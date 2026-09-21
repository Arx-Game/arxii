---
name: issue-to-merged-pr
description: "Use when working on a GitHub issue from start to merged PR. Picks up an issue (or prompts for one), assesses discovery, collaborates on the product brief and technical spec, implements after member approval except for validated lightweight work, opens a PR, watches CI and fixes failures, and handles post-merge cleanup including filing follow-up issues. Polytoken-native: orchestrates the ported brainstorming + writing-plans + using-git-worktrees skills."
compatibility: polytoken-only
---

# shared-assets-from: issue-to-merged-pr

# issue-to-merged-pr (Polytoken)

This skill carries a GitHub issue from pickup through to a merged PR. It is
**multi-invocation**: the agent works up to a human gate, then exits while review
is async. Standard/heavyweight work has **two** such gates — **spec review on the
issue** (a member applies the `spec:approved` label) and **code review on the PR**
— plus CI. A clearly bounded lightweight issue may bypass the spec gate only with
its validated discovery marker. The user re-invokes the skill in a new session;
the agent reads the issue + PR state and picks up the right phase.

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

Read the `status:*`, `spec:approved`, and discovery state in the issue body. The
actual discovery marker must be outside the `<!-- spec:start -->` /
`<!-- spec:end -->` region. Run `tools/skills/issue-to-merged-pr/scripts/validate-discovery.sh <N>` whenever a marker is present or a phase transition is requested. First match wins:

| issue state | Phase |
|---|---|
| `status:implementing` with `discovery:lane=lightweight;state=complete`, no `spec:approved` | **Lightweight implementation** — the explicit bounded-work exception; continue building |
| `status:spec-draft` with a complete lightweight marker, no `spec:approved` | **Lightweight handoff** — validate, flip to `status:implementing`, then build |
| `status:spec-draft` with standard/heavyweight `state=awaiting-stakeholder` | **Discovery-awaiting** — exit; the stakeholder conversation is active |
| `status:spec-draft` with standard/heavyweight `state=complete` | **Technical design** — draft or revise the technical spec, then use normal spec review |
| `spec:approved` present, no open PR yet | **Implementation** — flip `status:spec-review`→`status:implementing`, then build |
| `status:spec-review`, no `spec:approved` | **Await-approval** — spec is on the issue; a member must apply `spec:approved`. Exit (review is on the human). |
| `status:spec-draft` without a valid discovery marker (or no `<!-- spec:start -->` marker) | **Discovery assessment** — assess the lane before any design skip |
| no `status:*` label | **Pickup** (fresh) |

A complete lightweight marker is the only path to `status:implementing` without
`spec:approved`. A standard/heavyweight packet still requires the member-only
spec gate after its product brief and technical design are complete.

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
- **STEP 0 (mandatory, before anything else):** Run `scripts/start-work.sh <N>`.
  This assigns the issue to you, applies `status:spec-draft`, creates the
  feature branch, and creates the worktree at `.claude/worktrees/<branch>`.
  **Do not read the issue body, inspect code, or begin design before this
  succeeds.** If it exits 3 (assigned to another user), the issue is claimed —
  stop and pick another. It delegates to `pickup-issue.sh` (claim + branch), then
  creates the worktree in one call, and emits JSON including `worktree_path`.
  `start-work.sh` is the **single mandatory first call** — it replaces the prior
  `pickup-issue.sh` + separate worktree-creation sequence. Skipping it is the #1
  cause of duplicate work (two sessions on the same issue because neither
  assigned it).
- After it succeeds, `pushd` into the emitted `worktree_path` so all subsequent
  file operations land in the worktree, not the main checkout:

  ```bash
  START_JSON=$(scripts/start-work.sh <N>)
  pushd "$(jq -r '.worktree_path' <<<"$START_JSON")"
  ```

  Do NOT run `git worktree add` or invoke `using-git-worktrees` Step 1a/1b again
  — `start-work.sh` already created the git worktree. The `using-git-worktrees`
  skill's Step 0 will detect you're already isolated and skip creation; that's
  the expected path on re-entry.

- **Model selection.** Read the `model` and `complexity` fields from the emitted
  JSON. `pickup-issue.sh` derives the model from the `complexity:*` label, with
  tier names overridable via `ISSUE_MODEL_HIGH` / `ISSUE_MODEL_MEDIUM` /
  `ISSUE_MODEL_LOW` env vars (defaults are Claude Code tiers; set them to
  umans-* models for Polytoken). If `model` is non-empty and the harness supports
  a model switch, switch now — before any design, planning, or implementation.

### 2. Discovery and design

Every claimed issue gets a quick **Discovery assessment** before any type-label or
short-issue heuristic can skip collaboration. Record this visible section before
the `<!-- spec:start -->` marker with Outcome, Success signal, Stakeholder
provenance, Impact, and Lane rationale. Use roles or approved pseudonyms in
public artifacts and redact private IC/OOC details. A type label is only a
candidate signal.
If there is an outcome-changing fork, user-facing impact, meaningful provenance
uncertainty, or material risk, select standard/heavyweight even when the issue is
labeled `docs` or `chore`.

For clearly bounded work, write `<!-- discovery:lane=lightweight;state=complete -->`
outside the spec markers. Run
`tools/skills/issue-to-merged-pr/scripts/validate-discovery.sh <N>`, flip
`status:spec-draft` to `status:implementing`, and proceed without `spec:approved`.
Keep the reason visible. Do not use this lane merely because a label looks simple.

For standard/heavyweight work, write the awaiting marker outside the spec markers
and invoke the ported `brainstorming` skill. The root agent and stakeholder
brainstorm together to produce a product brief/PRD: users, desired outcome,
success signal, non-goals, provenance, assumptions, 1–3 options with consequences,
and concrete scenarios or state transitions. The agent facilitates and records
choices; it must not silently choose product taste or priorities. Dispatch
`intent-ambiguity-critic` and `scope-simplicity-critic` in parallel before the
stakeholder conversation; fold their evidence into the PRD, then record the
stakeholder ruling.

For visual or high-risk work, use `tools/skills/demoing-a-feature/SKILL.md` before
technical approval. Produce two or more low-cost, read-only demo directions or screenshot variants,
show the meaningful tradeoffs, and let the stakeholder
choose, reject, or amend one in chat. Republish the artifact and record the ruling
before technical design. Use concrete traces, payloads, or state transitions for
nonvisual work. `demo-fidelity-reviewer` later checks the built surface against the
approved direction; it does not replace this product conversation.

When the conversation is complete, retain the marker with `state=complete`, run
the validator, and draft the technical spec in a separate section. Standard and
heavyweight work still follows the normal `status:spec-review` → member-only
`spec:approved` gate. Keep discovery markers outside the spec markers so a spec
rewrite cannot delete or change the conversation state.

The ported skill already bakes in:
- **Spec destination:** the issue body, between `<!-- spec:start -->` and
  `<!-- spec:end -->` markers (`gh issue edit <N> --body-file`), using
  `docs/spec-template.md`'s section layout. No committed spec file.
- **Mandatory `verify-against-code` pass:** before the spec is finalized, run
  `tools/skills/verify-against-code/` and embed the anti-reinvention ledger.
- **Mandatory `schema-shape` pass:** whenever the design proposes a new model,
  table, FK, column, or primary-key choice, run `tools/skills/schema-shape/` and
  embed its six-question answers.
- **Spec-review dispatch:** use the prompt at
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
(`tools/skills/using-git-worktrees/`) — but if you ran `start-work.sh` during
Pickup, the worktree already exists; the `using-git-worktrees` skill's Step 0
will detect you're already isolated and skip creation. Then invoke the ported
**`writing-plans`** skill (`tools/skills/writing-plans/`) to produce the
**ephemeral** plan (worktree-only, never committed).

The ported `writing-plans` skill goes straight to implementation (it does not
prompt subagent-vs-inline). Work through the plan task-by-task in this session,
committing after each. Follow the plan if one exists; otherwise implement
directly.

### Conditional implementation-quality review

Inspect the actual diff before opening the PR and record selected/skipped lanes in
PR Notes. Dispatch only matching reviewers, not a permanent council. Existing
narrow reviewers take precedence: schema/model changes use
`schema-shape-reviewer`; migrations use `migration-reviewer`; shared guards or
broad abstractions use `blast-radius-reviewer` plus the simplicity critic; hooks,
network boundaries, or mocks use `mock-fidelity-reviewer`; player-facing outcomes
use `outcome-delivery-reviewer`; typeclass creation uses
`typeclass-creation-reviewer`; derived domains use
`derived-classifier-reviewer`; enumerated domains use `enumerated-set-reviewer`;
Portal code uses `portal-code-deploy-reviewer`; approved visual work uses
`demo-fidelity-reviewer`.

For auth/permissions, private or IC/OOC audience, query/resource cost, recovery,
or operational burden without a narrower reviewer, invoke the Polytoken-only
`.polytoken/subagents/code-reviewer.md` with exactly the selected lens. Its report
must include file/line evidence, consequence, severity, confidence,
recommendation, and a disposition: fix, accepted consequence with rationale,
substantial follow-up, or informational. Do not claim this reviewer is a Claude
workflow equivalent; Claude uses the tracked
`tools/agents/implementation-quality-reviewer.md`. Unresolved high-impact
findings block the PR. Set the optional `PR_DISCOVERY_LANE` rationale (the lane itself is derived from the
validated issue marker), plus `PR_BRAINSTORM_DEMO` and `PR_QUALITY_REVIEW` with the
collaborative PRD or explicit lightweight non-applicability and selected/skipped
reviewer dispositions. `open-pr.sh` rejects missing or placeholder values.

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

**PR creation is automatic — do not ask the operator for approval.** Once
implementation is complete, tests pass, docs are updated, and the committed
review evidence report validates against the reviewed code revision (the parent of the evidence commit), push the branch and open the PR.
`open-pr.sh` is a hard pre-PR gate: it requires provenance, the ordinary user
path, visual screenshots when a design/demo exists, one verdict per mandatory
criterion, and no unresolved findings. A green build is not acceptance evidence.
`open-pr.sh` requires every PR to close its issue (`Closes`). There is no
keep-open override: for partial work, file a child issue for the remaining
scope and make this PR close that child instead of leaving the parent open.

Before opening, dispatch the local reviewer required by the issue. For a design/demo issue, this is `demo-fidelity-reviewer`; it must render the application, inspect screenshots with a vision-capable model, complete the visual checklist, and write the report. `open-pr.sh` blocks until that report names a reviewer and has a PASS verdict. Set `PR_EVIDENCE_FILE` to a local report (a repository or scratch path), or set `PR_EVIDENCE_URL` to the GitHub issue/PR comment where the reviewer posted it. Compose the PR body's substitution
values. For each deferred follow-up, call
`scripts/file-followup.sh <title> <body-path> <labels...>` NOW (before opening
the PR) and collect the issue numbers. **Before filing each follow-up, run the
`verify-against-code` pass on its premise** — drop it if already built; file
design-open items as `needs-design` questions, not asserted work.

```bash
PR_EVIDENCE_FILE="a scratch review report" \
PR_SUMMARY="..." PR_RAN_OR_SKIPPED="ran" PR_SYNC_SUMMARY="..." \
  scripts/open-pr.sh <branch> <issue-N> <followup-1> <followup-2> ...
```

The PR body links the committed report and uses `Closes #<issue>`. CI rejects
non-Dependabot PRs without an explicit closing issue reference, and partial
work must close a child issue rather than leaving its parent open. Dependabot
PRs are exempt because automated dependency updates may lack issues.

**Do NOT run `uv run pre-commit run --all-files` (or whole-repo test suites) as a
pre-push precheck — it can crash this devcontainer.** The per-file hooks already
ran at commit; CI's `pre-commit` job is the gate. Only if the branch used
`--no-verify` commits, scope the catch-up to the diff (never `--all-files`):
`uv run pre-commit run --from-ref origin/main --to-ref HEAD`. That form clears the
worktree while hooks run (#3814), so run it only when no other agent has
uncommitted work in the worktree.

### 6. CI watch

Run `scripts/watch-ci.sh <pr-N>`. Outcomes:
- `OK` (exit 0): run `scripts/enqueue-pr.sh <pr-N>`. It revalidates the
  committed report against the reviewed code revision before arming auto-merge. Then post a
  brief status comment and exit the session. **Do NOT re-sync or merge by
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
- `start-work.sh` exits 3 (issue assigned to another user). Do NOT proceed; the
  issue is claimed — pick another.
- During brainstorm, scope feels fundamentally different from the title — post
  on the original issue suggesting a split, exit before opening any PR.
- Any `gh` command fails with auth errors. Surface the error and `gh auth
  status` output.
- A takeaway-capture post would contain a secret-pattern match. Abort the post,
  surface the offending line, exit without commenting.

Each bail writes a structured PR or issue comment with: what was attempted,
where it stopped, what the human should decide.

## Issue/demo image fallback

When a player-facing spec needs screenshots on the issue before a PR exists and
interactive Artifact publishing is unavailable, push the branch and run
`tools/skills/issue-to-merged-pr/scripts/publish-issue-images.sh <issue> <branch> <image>...`.
It uploads through the GitHub Contents API and posts immutable raw URLs in an
issue comment. Use `--dry-run` first and verify the comment's `.body_html`
contains one `<img>` per input. The full sequence, cleanup guidance, and
privacy warning are in `tools/skills/issue-to-merged-pr/references/evidence-screenshots-not-in-main.md`.

## Quick reference

| Need | Script |
|---|---|
| Start work on issue N | `scripts/start-work.sh N` |
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
