# Agent Skills

Project-specific skills (the open "Agent Skills" `SKILL.md` format) that support
the development workflow. `tools/skills/` is the single canonical home.

In the devcontainer, these skills are **installed automatically** —
`.devcontainer/post-create.sh` symlinks each `tools/skills/<name>/` directory
into `~/.claude/skills/` on container creation, except skills marked
`compatibility: polytoken-only` (those are Polytoken-exclusive; see below). No
manual copy needed; changes you make to a skill here are picked up immediately
because the symlink points back at this directory.

For bare-metal usage, see the options below.

## Two harnesses: Claude Code and polytoken

The devcontainer runs both Claude Code and the [polytoken](../../.devcontainer/polytoken.md)
harness, and both read the same `SKILL.md` format. They differ only in **where**
they discover skills:

- **Claude Code** reads `~/.claude/skills/` and **follows symlinks**, so the
  symlink loop above exposes harness-agnostic skills to it (but skips
  `polytoken-only` skills to avoid colliding with same-named `superpowers`
  plugin skills).
- **polytoken** reads `.polytoken/skills/` (project-level) and **does not follow
  symlinks**, so it needs real files there.

A skill opts into the polytoken mirror by declaring **`compatibility: polytoken`**
in its frontmatter. `.devcontainer/post-create.sh` runs
`tools/skills/sync-polytoken-skills.sh`, which copies exactly those skills into
the generated (gitignored) `.polytoken/skills/`. After editing a bridged skill
mid-session, re-run `just sync-polytoken-skills`.

There are two marker variants:

- **`compatibility: polytoken`** — additive. The skill is mirrored into
  `.polytoken/skills/` *and* still symlinked into Claude Code via
  `~/.claude/skills/`. Use for harness-agnostic skills that don't collide with
  anything (e.g. `github-operations`, `verify-against-code`).
- **`compatibility: polytoken-only`** — Polytoken-exclusive. Mirrored into
  `.polytoken/skills/` but **skipped** by the Claude Code symlink loop. Use for
  skills that would collide with a same-named `superpowers` plugin skill in
  Claude Code (e.g. the ported `brainstorming`, `writing-plans`,
  `using-git-worktrees`, and the `issue-to-merged-pr-polytoken` orchestration
  skill). This keeps a colleague's Claude Code setup untouched.

Only harness-agnostic skills carry the marker. Skills coupled to Claude Code
(e.g. `issue-to-merged-pr`, which orchestrates the `superpowers` plugin) stay
Claude-Code-only — they have no marker and never reach polytoken.

## Bare-metal install

### Linux / macOS (recommended)

```bash
for skill in tools/skills/*/; do
  name=$(basename "$skill")
  # Skip Polytoken-exclusive skills — they'd collide with same-named
  # superpowers plugin skills in Claude Code.
  grep -q '^compatibility:[[:space:]]*polytoken-only$' "$skill/SKILL.md" 2>/dev/null && continue
  ln -sfn "$(pwd)/${skill%/}" "$HOME/.claude/skills/$name"
done
```

`-sfn` is idempotent — re-run any time. Edits to skill files are picked
up immediately by Claude Code (the symlink points back at this
directory). To mirror the `polytoken` / `polytoken-only` skills into
Polytoken on bare metal, run `bash tools/skills/sync-polytoken-skills.sh`.

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
[design doc](issue-to-merged-pr/references/design.md).

### codebase-indexing

Regenerates `docs/systems/MODEL_MAP.md` — an auto-generated map of all
Django model relationships and service function signatures. Prevents
expensive codebase searches when working across multiple apps.

### github-operations

Conventions for `gh` CLI work: read the issue/PR number from the URL the
create command returns (never compute it — issues and PRs share one counter,
so it is rarely `N+1`), verify number↔title before any mutation, and keep
issue/PR writes to one-per-message. Permanent good practice.

### design-vocabulary

Shared vocabulary for judging interface design — depth, interface, seam,
leverage, locality, the deletion test, "one adapter = a hypothetical seam,
two = a real one." Concepts only: it does **not** rename "module" or ban
"component/service/API". Anchored on the repo's action-dispatch seam; leads with
the plain principle in user-facing prose.

### architecture-cleanup

Audits a subsystem for shallow modules and leaky seams via Explore subagents and
the deletion test, then produces a **markdown** report (no HTML/Mermaid — this is
a headless repo) of candidate refactors ranked Strong / Worth-exploring /
Speculative. Flags conflicts with recorded ADRs.

### domain-glossary-and-adr

Keeps the `AGENT_GLOSSARY.md` files and `docs/adr/` log current and used: read
glossary terms before designing, update them in the same PR, and offer an ADR only
on the three-part bar (hard to reverse, surprising, a real trade-off). Enforces the
spoiler wall — neutral phrasing in the repo, rationale in private memory.

## Updating skills

In the devcontainer or Linux/macOS bare-metal: just edit the files
here — the symlink picks up changes. On Windows non-symlink installs,
re-run `xcopy` after edits.
