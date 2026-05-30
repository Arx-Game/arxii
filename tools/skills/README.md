# Claude Code Skills

Project-specific skills for Claude Code that support development workflow.

In the devcontainer, these skills are **installed automatically** —
`.devcontainer/post-create.sh` symlinks every `tools/skills/<name>/`
directory into `~/.claude/skills/` on container creation. No manual
copy needed; changes you make to a skill here are picked up
immediately because the symlink points back at this directory.

For bare-metal usage, see the options below.

## Bare-metal install

### Linux / macOS (recommended)

```bash
for skill in tools/skills/*/; do
  name=$(basename "$skill")
  ln -sfn "$(pwd)/${skill%/}" "$HOME/.claude/skills/$name"
done
```

`-sfn` is idempotent — re-run any time. Edits to skill files are picked
up immediately by Claude Code (the symlink points back at this
directory).

### Windows

Symlinks on Windows require developer mode or an elevated shell, so
the simpler path is to copy:

```cmd
xcopy /E /I tools\skills\* %USERPROFILE%\.claude\skills\
```

Drawback: this is a one-time copy — you must re-run it after editing a
skill here. (Enabling developer mode and using `mklink /J` for junctions
is the symlink-equivalent on Windows if you want the live-update
behavior.)

## Available Skills

### issue-to-merged-pr

Carries a GitHub issue through to a merged PR with minimal human gating:
brainstorm/spec/plan, implementation, PR, CI watch and fix loop,
post-merge cleanup. Multi-invocation, GitHub-as-truth. See
[issue-to-merged-pr/README.md](issue-to-merged-pr/README.md) and the
[design spec](../../docs/superpowers/specs/2026-05-25-issue-to-merged-pr-design.md).

### codebase-indexing

Regenerates `docs/systems/MODEL_MAP.md` — an auto-generated map of all
Django model relationships and service function signatures. Prevents
expensive codebase searches when working across multiple apps.

### grounding-before-action `[TEMP — HARNESS-BUNDLING-WORKAROUND]`

**Temporary workaround for a Claude Code 2.1.158 regression** where a tool
result co-emitted in the same assistant message as the call it depends on is
invisible at compose time, causing the model to confabulate the result and act
on it. Enforces un-bundling `AskUserQuestion`/result-claims from their tool
calls and verifying issue number↔title before mutations. **Delete this skill
when the harness is fixed** — removal manifest + test in GH #647.

## Updating skills

In the devcontainer or Linux/macOS bare-metal: just edit the files
here — the symlink picks up changes. On Windows non-symlink installs,
re-run `xcopy` after edits.
