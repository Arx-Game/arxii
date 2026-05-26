---
name: workflow-friction-audit
description: Use when you notice a recurring tool-call failure or environment-quirk pattern. Logs the friction; when ≥5 entries accumulate, proposes CLAUDE.md edits (apply now) or files a follow-up issue. Replaces the permission-prompt model that doesn't apply in the devcontainer (where Claude runs with --dangerously-skip-permissions).
---

# Workflow Friction Audit

## Purpose

Track recurring **tool-call failures** and **environment quirks** in a persistent log. When enough entries accumulate, group them by root cause and propose permanent fixes — CLAUDE.md edits, script updates, or follow-up issues.

This replaces the deleted permission-prompt-tracking version that produced nothing to observe in the devcontainer.

## When to log

Append an entry when you notice any of:

- A `Bash` tool call exited non-zero in a way that suggests a recurring environment quirk (not a normal test/lint failure during the work itself).
- A tool name or path you expected to exist didn't.
- An external tool (`gh`, `git`, `arx`, etc.) errored with a message that looks pattern-shaped, not one-off.
- You retried with a different approach because the first didn't work, and the workaround feels like it'll recur.

One entry per noticed event. No deduplication at log-time — that's the audit's job.

## Log file

Path: `/home/vscode/.claude/projects/-workspaces-arxii/memory/friction-log.md`

This directory is inside the `arxii-claude-home` named volume, so the log survives `dc-down/dc-up`. It is NOT indexed in `MEMORY.md` (friction is ephemeral; pruned after each audit).

Append entries in this format:

```markdown
## YYYY-MM-DD — <short-category>
- **Event:** <one-sentence summary — NOT raw output>
- **Context:** <2-3 sentences: what we were trying, why this happened, suspected root cause>
- **Suspected fix:** <CLAUDE.md edit, script update, doc note, or "investigate further">
```

Categories are free-form short tags — examples: `bash-error`, `gh-label-mismatch`, `path-not-found`, `cli-args-changed`, `retry-pattern`. The audit groups by these.

If the file doesn't exist yet, create it with a single H1 header `# Friction Log` and append below.

## Capture discipline — secrets

**Entries are human-written summaries, not raw output paste-throughs.** Layer 1 of the three-layer redaction discipline.

- Summarize the error type. E.g., `gh api 401 (auth failure on repos/.../contents)` — not the full error block.
- Never log: `env` output, `curl` requests/responses, anything with `Authorization:` headers, `.env` file contents, anything matching the patterns in `secret-patterns-defaults.txt`.
- When in doubt, log the symptom (`gh push failed: permission denied`) not the detail (verbatim stderr).

## When to audit

When the log file currently contains **≥5 entries**, run the audit at the next user-facing turn boundary. Include the consolidated proposal in your next response to the user rather than interrupting mid-task.

"User-facing turn boundary" = the next time you're about to send a text response back to the user (not mid-tool-call sequence). If you're in the middle of an `executing-plans` run with no natural user-facing turn coming up soon, defer to the next pause.

Pruning after each audit is the state-keeping mechanism — the entry count IS the "since last audit" count. There is no separate audit-counter file.

## The audit

### Step 1: Read the log and group entries

Read `/home/vscode/.claude/projects/-workspaces-arxii/memory/friction-log.md`. Group entries by root cause (often, but not always, by their category tag). A group is ≥2 entries with the same underlying cause; isolated single entries can be their own group if the fix is concrete.

### Step 2: Draft the consolidated proposal

One Markdown document. For each group:

```markdown
### Group: <short label>

**Pattern (N entries):** <1-2 sentence summary of the recurring cause>

**Proposed action:** <ONE concrete action — CLAUDE.md diff, script update, "investigate further", etc.>
```

End with a brief overall summary (one paragraph).

### Step 3: Layer 2 — pre-output regex sweep

Before showing the proposal to the user, write it to a temp file and scan for secrets:

```bash
PROPOSAL_TMP=$(mktemp)
# Write the proposal text to "$PROPOSAL_TMP" via the Write tool or a heredoc.

USER_PATTERNS=tools/skills/workflow-friction-audit/secret-patterns.txt
if [ -f "$USER_PATTERNS" ]; then
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt -f "$USER_PATTERNS" "$PROPOSAL_TMP"
else
  grep -E -n -f tools/skills/workflow-friction-audit/secret-patterns-defaults.txt "$PROPOSAL_TMP"
fi
```

Interpret the exit code:
- **Exit 0** (match found): abort the audit. Surface to the user: "Proposal contains a potential secret matching `<pattern>` at line N (showing: `<the matching line>`). Please redact manually before continuing." Do not auto-redact. Do not prune the log.
- **Exit 1** (no match): continue to Step 4.

### Step 4: Offer two paths to the user

Show the user the proposal, then ask:

> "Two paths from here:
> 1. **Apply now** — I'll show the unified diff for any CLAUDE.md / script edits in the proposal; you approve (whole batch or per-group), and I'll land the changes and prune the log.
> 2. **File as issue** — I'll call `file-followup.sh` with the proposal as the issue body; you review later via normal PR flow. Log prunes once the issue is filed.
>
> Which one?"

Use `AskUserQuestion` for a structured response, or plain text — your call based on session context.

### Step 5a: Apply now (Path A)

For each group's proposed action that's a file edit:
- Show the unified diff (use `Edit` tool's preview, or write out the `old_string` → `new_string` blocks).
- Ask which groups the user approves (or "all").
- Apply approved edits via `Edit` tool.

Pruning rule:
- Entries that fed an **approved** group → remove from the log.
- Entries that fed a **rejected** group → leave in place (they re-surface on the next audit).
- Entries not in any group → leave in place.

Use `Edit` on the log file to remove the approved entries.

### Step 5b: File as issue (Path B)

Run Layer 3 — the post-time hard gate — by re-running the grep from Step 3 on the final issue body (which is the same proposal text; if you edited it after Step 3, re-scan). If exit 0, abort with the same user-surfaced message.

Then:

```bash
ISSUE_NUM=$(bash tools/skills/issue-to-merged-pr/scripts/file-followup.sh \
  "Friction audit: <short summary>" \
  "$PROPOSAL_TMP" \
  enhancement)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
echo "Filed: https://github.com/$REPO/issues/$ISSUE_NUM"
```

(Read the repo dynamically via `gh repo view` — never hardcode the org/name.)

If `file-followup.sh` exits 0:
- Surface the issue URL in your user-facing message.
- Prune ALL entries that fed the proposal from the log (the issue is now the authoritative record).

If `file-followup.sh` exits non-zero:
- Surface the error to the user.
- **Do NOT prune** — the log stays intact for retry.

## Layer 3 — post-time gate (also applies to takeaway-capture)

This skill's secret-redaction patterns and the `grep -E -f` mechanism are reused by the takeaway-capture sub-steps in `tools/skills/issue-to-merged-pr/SKILL.md`. Same defaults file, same user-extension file, same abort discipline. Before any `comment-on-issue.sh` call from that skill's takeaway path, run the same scan.

## Anti-patterns

- **Don't log normal test failures during the task.** "My code change broke a test, then I fixed it" is not friction — it's the work. Friction is environmental, recurring, fix-elsewhere-in-the-stack.
- **Don't paste raw output into entries.** That's where secrets leak. Summarize.
- **Don't add overly broad CLAUDE.md edits** ("never use `gh`"). The redesign's whole point is targeted fixes for specific recurring patterns.
- **Don't audit during single-task flow.** Wait for a natural turn boundary.
- **Don't auto-apply CLAUDE.md edits.** User always approves before edits land (Path A) or before an issue is filed (Path B).

## Calibration

When in doubt about whether something is worth logging: **log it.** The audit step's grouping and the user's Path-A rejection are the filters. Better to over-log and have entries pruned than to miss a real pattern.

When in doubt about whether something is worth proposing in an audit: **propose it cautiously.** A weak proposal the user rejects leaves entries in the log for the next audit to revisit with more data. A strong proposal that gets approved becomes a permanent fix.
