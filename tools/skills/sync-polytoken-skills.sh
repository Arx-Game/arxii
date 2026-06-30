#!/usr/bin/env bash
# Mirror harness-agnostic skills into .polytoken/skills/ so polytoken discovers
# them. A skill opts in by declaring `compatibility: polytoken` (additive:
# also kept in Claude Code) or `compatibility: polytoken-only` (Polytoken-
# exclusive: skipped by the Claude Code symlink loop to avoid colliding with a
# same-named superpowers plugin skill). Claude Code ignores both fields.
#
# Why a copy and not a symlink: polytoken skips symlinked paths during skill
# discovery, so the files must be real. Claude Code DOES follow symlinks and gets
# the same skills via ~/.claude/skills (see .devcontainer/post-create.sh), so
# tools/skills/ stays the single canonical home. .polytoken/skills/ is generated
# (gitignored). Re-run after editing a bridged skill: `just sync-polytoken-skills`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/tools/skills"
DEST="$REPO_ROOT/.polytoken/skills"

# Rebuild from scratch so a skill that drops the marker (or is deleted) does not
# linger in the mirror.
rm -rf "$DEST"
mkdir -p "$DEST"

# True iff the file's YAML frontmatter (the first --- ... --- block) declares a
# polytoken opt-in marker — either `compatibility: polytoken` (additive: also
# mirrored to Polytoken, but still symlinked into Claude Code) or
# `compatibility: polytoken-only` (Polytoken-exclusive: NOT symlinked into
# Claude Code, because it would collide with a same-named superpowers plugin
# skill). Scoped to the frontmatter so a body mention never false-matches.
declares_marker() {
  awk '
    NR == 1            { if ($0 != "---") exit 1; next }
    $0 == "---"        { exit found ? 0 : 1 }
    /^compatibility:[[:space:]]*polytoken(-only)?[[:space:]]*$/ { found = 1 }
    END                { exit found ? 0 : 1 }
  ' "$1"
}

count=0
shopt -s nullglob
for skill_md in "$SRC"/*/SKILL.md; do
  if declares_marker "$skill_md"; then
    name="$(basename "$(dirname "$skill_md")")"
    cp -R "$SRC/$name" "$DEST/$name"
    count=$((count + 1))
    echo "  + $name"
  fi
done
shopt -u nullglob

# Some Polytoken skills reuse shared assets (scripts/, templates/, prompts) that
# live in a *sibling* skill directory rather than their own. The canonical case
# is issue-to-merged-pr-polytoken, whose SKILL.md references scripts/... that
# actually live in issue-to-merged-pr/scripts/. Copy those shared assets into
# the mirrored skill so its relative scripts/ references resolve at runtime.
# Declared via a `# shared-assets-from: <sibling-dir>` line in the SKILL.md.
shopt -s nullglob
for skill_md in "$DEST"/*/SKILL.md; do
  sibling=$(sed -n 's/^# shared-assets-from:[[:space:]]*//p' "$skill_md" | head -1 | tr -d '[:space:]')
  [[ -n "$sibling" ]] || continue
  [[ -d "$SRC/$sibling" ]] || { echo "  ! $sibling (shared-assets-from target missing)" >&2; continue; }
  name="$(basename "$(dirname "$skill_md")")"
  for asset in "$SRC/$sibling"/*; do
    base=$(basename "$asset")
    [[ "$base" == "SKILL.md" || "$base" == "README.md" || "$base" == "references" ]] && continue
    cp -R "$asset" "$DEST/$name/$base"
  done
  echo "    ↳ shared assets from $sibling"
done
shopt -u nullglob

echo "sync-polytoken-skills: copied $count skill(s) to .polytoken/skills/"
