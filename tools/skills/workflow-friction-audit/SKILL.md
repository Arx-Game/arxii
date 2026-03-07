---
name: workflow-friction-audit
description: Use when a tool call is denied, a command fails repeatedly, or you notice a workaround pattern emerging. Also use at session end to review accumulated friction and propose permanent fixes.
---

# Workflow Friction Audit

## Overview

Track recurring workflow friction (permission denials, repeated failures, workarounds) in a persistent log. Periodically review the log and propose permanent fixes — new allowed-tools rules, CLAUDE.md updates, or workflow changes.

## When to Log Friction

Log to the project's auto-memory friction file (e.g., `memory/friction.md` in your Claude projects directory) when:
- A tool call is **denied** by the user
- A command **fails 2+ times** with the same root cause
- You find yourself using a **workaround** for something that should be direct
- A permission prompt fires for something that's clearly **read-only or safe**
- You need to **retry with different flags/paths** due to environment issues

## Log Format

Append entries using this format:

```markdown
## [DATE] Category: Brief description
- **What happened:** One sentence
- **Frequency:** First occurrence / Repeated (N times)
- **Suggested fix:** Concrete action (e.g., add `Bash(command*)` to settings.local.json)
- **Priority:** Low / Medium / High (based on frequency × impact)
```

Categories: `permission-denied`, `command-failure`, `workaround`, `environment`, `missing-tool`

## When to Review

Review the friction log and propose fixes when:
- The user asks about permissions or workflow efficiency
- You notice 3+ entries in the same category
- At session end if friction was logged during the session

## Review Process

1. Read the friction log
2. Group entries by root cause
3. For each group, propose ONE of:
   - **Add allowed-tool rule** — if the command is safe and frequently prompted
   - **Update CLAUDE.md** — if a workflow pattern should be documented
   - **Update memory** — if it's a recurring environment quirk
   - **No action** — if the friction was a one-off or user intentionally wants the prompt
4. Present proposals to user for approval
5. Apply approved changes and remove resolved entries from the log

## Permission File Locations

```
<project>/.claude/settings.local.json  — project-level (codebase-specific commands)
~/.claude/settings.json                — global (general read-only shell commands)
```

## Pattern: Safe Command Variants

```
Bash(command subcommand:*) — specific subcommand
Bash(command *)            — any args (use for read-only commands only)
```

## Common Mistakes

- Don't add overly broad rules like `Bash(python:*)` — these match destructive operations
- Don't log one-off failures that were user error
- Don't propose removing prompts the user explicitly wants (git push, destructive ops)
- Prune resolved entries so the log stays actionable
