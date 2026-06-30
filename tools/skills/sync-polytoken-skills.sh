#!/usr/bin/env bash
# Mirror harness-agnostic skills into .polytoken/skills/ so polytoken discovers
# them. A skill opts in by declaring `compatibility: polytoken` in its SKILL.md
# frontmatter (Claude Code ignores the field).
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

# True iff the file's YAML frontmatter (the first --- ... --- block) declares the
# opt-in marker. Scoped to the frontmatter so a body mention never false-matches.
declares_marker() {
  awk '
    NR == 1            { if ($0 != "---") exit 1; next }
    $0 == "---"        { exit found ? 0 : 1 }
    /^compatibility:[[:space:]]*polytoken[[:space:]]*$/ { found = 1 }
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

echo "sync-polytoken-skills: copied $count skill(s) to .polytoken/skills/"
