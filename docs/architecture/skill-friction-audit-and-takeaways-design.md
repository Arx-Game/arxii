# Skill: friction-audit redesign + takeaway-capture step

**Date:** 2026-05-26
**Closes:** #500, #504
**Related:** #505 (deferred login persistence), #501/#503 (issue-to-merged-pr origin)

## Goals

1. **Restore a friction-tracking skill** that works in the devcontainer environment, where Claude Code runs with `--dangerously-skip-permissions` and permission prompts never fire (so the deleted `workflow-friction-audit`'s "permission denial" trigger model produced nothing to observe).
2. **Add a takeaway-capture step** to `issue-to-merged-pr`'s SKILL.md lifecycle so non-obvious lessons surfaced during PR review or post-merge cleanup are carried forward as comments on related issues — discoverable by future agents who pick up adjacent work.

Both target the same problem class (signal extraction from agentic workflows) and ship together because they share the secret-redaction discipline below.

## Non-goals

- A hook-driven log capture mechanism for the friction skill. Logging is via Claude's voluntary invocation, not `PostToolUse` hooks. (Out of scope; see "Deferred" below.)
- Fixing the `~/.claude.json` persistence gap captured in #505.
- Replacing the existing auto-memory system. Friction log is a separate file, not indexed in `MEMORY.md`.

## Design — workflow-friction-audit (issue #500)

### Skill location

`tools/skills/workflow-friction-audit/SKILL.md` — same path as the deleted skill. The PR symlinks it into `~/.claude/skills/` via the existing `post-create.sh` loop.

### Trigger: logging

Claude invokes the skill when it notices any of:

- A `Bash` tool call exited non-zero in a way suggesting a recurring environment quirk (not normal test/lint failure during the task).
- A tool name or path the agent expected to exist didn't.
- An external tool (`gh`, `git`, `arx`, etc.) returned an error that looks pattern-shaped, not one-off.
- A retry-with-different-approach pattern Claude notices itself doing.

The skill logs ONE entry per noticed event. No deduplication at log-time — that's the audit's job.

### Log file

Path: `/home/vscode/.claude/projects/-workspaces-arxii/memory/friction-log.md`

This directory is inside the `arxii-claude-home` named volume, so the log survives `dc-down/dc-up` (same durability as the existing auto-memory).

Not indexed in `MEMORY.md`. Friction is ephemeral; pruned aggressively after each audit.

Entry format (append-only):

```markdown
## YYYY-MM-DD — <short-category>
- **Event:** <one-sentence summary of what failed/surprised — NOT raw output>
- **Context:** <2-3 sentences: what we were trying, why this happened, suspected root cause>
- **Suspected fix:** <CLAUDE.md edit, script update, doc note, or "investigate further">
```

Categories are free-form short tags (`bash-error`, `gh-label-mismatch`, `path-not-found`, etc.) — the audit step groups by these.

### Audit trigger

When the log file currently contains ≥5 entries, the skill fires at the next user-facing turn boundary. Claude includes the consolidated proposal in its next response to the user rather than interrupting mid-task.

(Pruning after each audit is the state-keeping mechanism — the entry count IS the "since last audit" count. There is no separate audit-counter file.)

"User-facing turn boundary" = the next time Claude is about to send a text response back to the user (not mid-tool-call sequence). If Claude is in the middle of an executing-plans run with no natural user-facing turn coming up soon, defer to the next pause.

### Audit output

ONE consolidated proposal:

1. Group log entries by root cause / category.
2. For each group, describe the recurring pattern in 1-2 sentences.
3. For each group, propose ONE concrete action: a CLAUDE.md edit (with the proposed diff inline), a script update, or "this needs broader discussion."

The skill then offers the user two paths:

**Path A — apply now.** Claude shows the unified diff for CLAUDE.md / script edits, user approves (whole batch or per-group). Approved edits land via `Edit` tool. Entries that fed an *approved* group are pruned; entries that fed a *rejected* group remain (so they re-surface on the next audit with whatever new context has accumulated). Entries not included in any group also remain.

**Path B — file as issue.** Claude calls `file-followup.sh` from `tools/skills/issue-to-merged-pr/scripts/` with the proposal as the issue body. Captures the returned issue number, surfaces the issue URL in the user-facing message so the user can follow up. Log entries that fed the proposal are pruned after `file-followup.sh` returns exit 0; on non-zero exit, NO pruning happens (the log stays intact for retry). The filed issue is now the authoritative record.

(Calling `file-followup.sh` and other scripts under `tools/skills/issue-to-merged-pr/scripts/` from the friction-audit and takeaway-capture paths is consistent with CLAUDE.md's `gh`-exception intent — those scripts ARE the sanctioned `gh` wrappers. No CLAUDE.md edit needed; the exception's wording covers the scripts themselves, not just the originating skill's direct lifecycle.)

Pruning is via `Edit` on the log file (remove the entries; keep the rest of the file). No backups, no archive — pruned content is gone. (If users want history, the audit proposal that became an issue is the durable record.)

### Secret-redaction discipline

Three layers — applies to BOTH the friction-audit and the takeaway-capture step.

**Layer 1 — log-time capture discipline.** Entries are human-written summaries, not raw output paste-throughs. The SKILL.md gives explicit rules:

- Summarize the error type. E.g., `gh api 401 (auth failure on repos/.../contents)` — not the full error block.
- Never log: `env` output, `curl` requests/responses, anything with `Authorization:` headers, `.env` file contents, any string matching the patterns in Layer 2.
- When in doubt, log the symptom (`gh push failed: permission denied`) not the detail (verbatim stderr).

**Layer 2 — pre-output regex sweep.** Before producing the consolidated proposal, the skill scans the proposal text against a denylist. Default patterns (also listed in SKILL.md):

```
ghp_[A-Za-z0-9]{36,}            github_pat_[A-Za-z0-9_]{60,}
gho_[A-Za-z0-9]{36,}            ghu_[A-Za-z0-9]{36,}
ghs_[A-Za-z0-9]{36,}            ghr_[A-Za-z0-9]{36,}
sk-[A-Za-z0-9]{20,}             xoxb-[A-Za-z0-9-]{20,}
xoxp-[A-Za-z0-9-]{20,}          AKIA[0-9A-Z]{16}
ASIA[0-9A-Z]{16}                -----BEGIN [A-Z ]+PRIVATE KEY-----
Authorization:\s*Bearer\s+\S+   AIza[0-9A-Za-z_-]{35}
```

User-extensible via `tools/skills/workflow-friction-audit/secret-patterns.txt` (gitignored — projects don't share secret-pattern lists). The skill loads this file on top of the defaults if it exists.

**Mechanism (how the scan runs):** Claude writes the candidate proposal to a temp file, then runs

```bash
grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt \
  $( [ -f tools/skills/workflow-friction-audit/secret-patterns.txt ] && \
     printf '%s' '-f tools/skills/workflow-friction-audit/secret-patterns.txt' ) \
  <proposal-tempfile>
```

via the `Bash` tool. Exit 0 (match found) → abort; exit 1 (no match) → continue. No wrapper script — the SKILL.md instructs Claude to run the command directly so the user sees the exact patterns being scanned.

On match: abort the audit and surface to the user — "proposal contains a potential secret matching `<pattern>` at line N, please redact manually before continuing." NO auto-redaction (a bad regex match auto-replacing the wrong substring is worse than the user dealing with it).

**Layer 3 — post-time hard gate.** Re-run the same scan on the final issue body immediately before calling `file-followup.sh`. If it matches → refuse to call the script, show the user the offending lines, exit. Belt-and-suspenders since the issue-filing path is the public-exposure risk.

### Files added

- `tools/skills/workflow-friction-audit/SKILL.md` — the skill itself.
- `tools/skills/workflow-friction-audit/secret-patterns-defaults.txt` — the default denylist (committed).
- Gitignore entry for `tools/skills/workflow-friction-audit/secret-patterns.txt` (user-local extension).

## Design — takeaway-capture step (issue #504)

Two new sub-steps injected into `tools/skills/issue-to-merged-pr/SKILL.md`, in the existing Steps 8 (PR-comment phase) and 9 (post-merge cleanup).

### Step 8 addition — after addressing review comments

After all actionable comments are committed (existing Step 8 behavior), before bumping the `<!-- last-addressed-comment: -->` marker, Claude evaluates each addressed comment for a takeaway worth carrying forward to related issues.

**Criteria for "takeaway worth posting":**
- Surfaces a gotcha, workflow weakness, or design decision that future agents working on related issues would benefit from.
- The insight is not already in CLAUDE.md (those go to the friction-audit's CLAUDE.md-edit path instead).
- The target issue exists and is open (or recently closed, < 90 days).

**Post unilaterally.** No user confirmation. Keeps the step lightweight. The bar is set by the criteria above; if Claude is unsure, skip the post (better to lose one takeaway than spam).

### Step 9 addition — post-merge cleanup

After `post-merge-cleanup.sh` emits its JSON, Claude reviews the merge for the same kind of takeaway. Targets: issues in `linked_issue_actions`, deferred follow-ups Claude filed during the PR's lifecycle. Same posting bar, same format.

### Comment format

Posted via `comment-on-issue.sh`:

```markdown
> **Takeaway from PR #<N>:** <one-sentence headline>
>
> <2-4 sentences of specific insight>
>
> Refs: PR #<N>, related: #<other-issues-if-any>
```

### Guardrails — ordering and scope

Explicit rules in SKILL.md, to prevent conflating "needs change in this PR" with "future takeaway":

1. **Default disposition: actionable.** For every review comment, first ask "can this be addressed in this PR?" Treat as actionable unless clearly out-of-scope (separable concern, different system, or reviewer explicitly framed it as future work).

2. **Takeaway evaluation runs AFTER all actionable work is committed.** Only once the PR is updated for every in-scope comment does Claude evaluate for cross-issue takeaways.

3. **A single comment can yield both.** Address the change in code AND post the takeaway on a related issue — not mutually exclusive.

4. **Insight about THIS PR's work stays in THIS PR.** The takeaway-comment path is for cross-issue carryforward only. PR-local insights go in the PR description or commit message.

5. **When uncertain about scope, address it.** Tie-breaker: if Claude can't decide whether a comment is in-scope or future work, address it now. User can ask for backout; cheaper than the comment getting filed elsewhere and forgotten.

### Secret-redaction applies

The same three-layer discipline from the friction-audit applies to takeaway comments. Posted comments are public; the post-time hard gate (Layer 3) runs before every `comment-on-issue.sh` call from the takeaway path.

### When to bail

Adds one entry to SKILL.md's "When to bail" section: if a takeaway comment would contain a secret-pattern match, abort the post and surface to the user. (Mirrors the friction-audit hard gate.)

### Files modified

- `tools/skills/issue-to-merged-pr/SKILL.md` — Steps 8 and 9 sub-step additions, "When to bail" entry, the secret-redaction cross-reference.

## CLAUDE.md addition — agent communication discipline

Folded in (not deferred to the audit's dogfood case) because the friction surfaced during the brainstorm itself: the user couldn't tell whether a sentence ending in `?` was a question to them or rhetorical agent self-talk.

Add a new short section to `CLAUDE.md`, placed between the opening paragraph and `## Git Workflow`:

```markdown
## Agent Communication

**Questions in user-facing text must be unambiguous.** If you write a sentence that ends in `?` in text the user sees, it must either:
- Be issued through `AskUserQuestion` (the answer is required to proceed), OR
- Be restated as a statement, not a question, when it's rhetorical self-direction (e.g., "Checking whether the skill expects a reviewer dispatch step." not "Does the skill expect a reviewer dispatch step?").

Ambiguous "?" sentences force the user to guess whether they're being asked to respond. When in doubt, no `?` in user-facing text outside of `AskUserQuestion`.
```

This is the friction-audit's pattern in miniature — a noticed-during-work ambiguity that turns into a permanent CLAUDE.md edit. We do it directly in this PR rather than dogfooding the audit on itself because the rule is small, clear, and the planner is already touching CLAUDE.md-edit infrastructure.

## Deferred / out-of-scope

- **Hook-driven log capture** for the friction-audit (auto-append on `PostToolUse` exit non-zero). Considered; deferred because: (a) requires settings.json hook config the user has to commit, (b) the voluntary-logging model is simpler to land first and validates the audit/proposal flow before adding the more reliable but heavier collector.
- **#505 — login persistence fix.** Already captured.
- **Repo type-label vocabulary mismatch.** The `pickup-issue.sh` script expects `feature/fix/chore/...` labels but this repo uses GitHub-default `enhancement/bug/documentation`. Surfaced during issue filing for this PR. Recording here as the **first dogfood entry** the friction-audit's audit step will likely produce against this repo: a real recurring friction. Not fixed in this PR (would expand scope to script + label vocabulary changes).

## Testing

Manual, scenario-based (no automated tests; these are skills, not code paths).

**workflow-friction-audit:**
1. Create a fresh friction-log.md with 5 fabricated entries, invoke the skill, verify the proposal lists groups + concrete actions.
2. Same, but include a fake `ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` in one entry's context — verify Layer 2 abort fires.
3. Same, but redact, then apply-now path — verify diff shown, partial-rejection of one group keeps THAT group's entries while pruning the approved groups'.
4. Same, but file-as-issue path — verify `file-followup.sh` called, issue body matches proposal, log pruned only after exit 0, returned URL surfaced.
5. **Dogfood case** — after this PR merges, invoke the audit against this repo's actual friction-log.md. Verify the `pickup-issue.sh` label vocabulary mismatch surfaces as a real entry (this PR's "Deferred" section predicts it will be the first dogfood finding). Closes the loop on the spec's own claim.

**takeaway-capture:**
1. Simulate a PR-comment-phase invocation with a review comment that's both actionable AND has takeaway value — verify code change made first, takeaway posted second, on the right issue.
2. Same, but with a comment that's clearly PR-local — verify NO takeaway post.
3. Post-merge cleanup invocation with a `linked_issue_actions: needs-attention` entry — verify takeaway posted on that issue.

## Open questions

None remaining. Brainstorming covered: log location, audit trigger, edit-application path, takeaway autonomy, secret redaction, scope-conflation guardrails.
