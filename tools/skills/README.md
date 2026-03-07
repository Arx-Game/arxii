# Claude Code Skills

Project-specific skills for Claude Code that support development workflow.

## Installation

Copy the skill directories into your personal Claude skills folder:

```bash
# Linux/Mac
cp -r tools/skills/* ~/.claude/skills/

# Windows
xcopy /E /I tools\skills\* %USERPROFILE%\.claude\skills\
```

Skills will be available in your next Claude Code session.

## Available Skills

### codebase-indexing
Regenerates `docs/systems/MODEL_MAP.md` — an auto-generated map of all Django model
relationships and service function signatures. Prevents expensive codebase searches
when working across multiple apps.

### workflow-friction-audit
Tracks recurring permission denials and workflow friction in a persistent log.
Periodically reviews the log and proposes permanent fixes to allowed-tools
configuration or CLAUDE.md.

## Updating

After editing skills here, re-copy to `~/.claude/skills/` to pick up changes.
