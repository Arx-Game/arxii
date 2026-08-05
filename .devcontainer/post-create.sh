#!/usr/bin/env bash
# Runs ONCE on container create, while the network is still open.
# Generates src/.env, installs project deps, applies DB schema.
set -euo pipefail

cd /workspaces/arxii
# Trust the workspace mise.toml first — mise activate skips PATH setup for an
# untrusted config and only prompts interactively afterward, which leaves the
# postCreate shell without uv/pnpm/etc. on PATH.
~/.local/bin/mise trust
eval "$(~/.local/bin/mise activate bash)"

# Git identity so commits made from inside the container land with the right
# author. ~/.gitconfig lives in the container's writable layer (not a named
# volume), so this needs to re-run on every fresh container — cheap and
# idempotent. Read each contributor's personal identity from dev.env
# (gitignored, per-contributor) so we don't have to hardcode anyone's name
# in the script.
if [[ -f .devcontainer/dev.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .devcontainer/dev.env
  set +a
fi
if [[ -n "${GIT_USER_NAME:-}" ]] && [[ -n "${GIT_USER_EMAIL:-}" ]]; then
  git config --global user.name "$GIT_USER_NAME"
  git config --global user.email "$GIT_USER_EMAIL"
else
  echo "[post-create] GIT_USER_NAME / GIT_USER_EMAIL not set in .devcontainer/dev.env." >&2
  echo "[post-create] Add them there (see sync-env.sh placeholders), or run" >&2
  echo "[post-create] 'git config --global user.name ...' yourself in the container." >&2
fi
# Safe-directory exemption: git in modern versions refuses to operate on a
# repo owned by a different uid than the current user. The bind-mounted repo
# is owned by whoever owns it on Windows, which isn't the container's vscode
# uid. Without this, every git command fails with "dubious ownership".
git config --global --add safe.directory /workspaces/arxii

# Named-volume mountpoints (.venv, frontend/node_modules) come up root-owned
# because they're sub-paths of a bind mount. Chown them before uv/pnpm try
# to write into them.
sudo /usr/local/bin/fix-volume-perms.sh

# Claude Code .claude.json relocation (issue #505).
#
# CLAUDE_CONFIG_DIR (set in docker-compose.yml) points Claude Code at
# /home/vscode/.claude/ for its config dir, so .claude.json lands INSIDE
# the arxii-claude-home named volume and persists across dc-down/dc-up.
#
# One-shot migration: if a pre-relocation .claude.json exists at the old
# default path (~/.claude.json) AND the new persisted location doesn't yet
# have one, move the file. This carries the user's existing login state
# forward on the first dc-up after this change lands, so they don't need
# to re-authenticate.
#
# Idempotent: subsequent runs see ~/.claude/.claude.json already present
# and skip. Never overwrites existing persisted state.
if [[ -f /home/vscode/.claude.json ]] && [[ ! -f /home/vscode/.claude/.claude.json ]]; then
  mv /home/vscode/.claude.json /home/vscode/.claude/.claude.json
  echo "[post-create] migrated ~/.claude.json -> ~/.claude/.claude.json (issue #505)"
fi

# settings.py requires SECRET_KEY and DATABASE_URL (django-environ, raises if
# missing). No .env ships in a fresh checkout. DATABASE_URL also arrives via
# compose env, but settings reads src/.env, so write it there too.
if [[ ! -f src/.env ]]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  cat > src/.env <<EOF
DEBUG=True
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgres://arxii:arxii@db:5432/arxiidev
EOF
fi

uv sync
pnpm install --dir frontend

# pre-commit hooks: install fresh inside the container.
#
# Background: if the host (Windows) ever ran `pre-commit install`, it baked
# its own absolute path into .git/config's core.hooksPath plus dropped a
# CRLF-shebang'd hook into .git/hooks/. Both survive the bind mount and
# silently bypass every commit's checks from inside Linux — git can't exec
# the CRLF shebang and `core.hooksPath` points at a non-existent Windows
# path. Unset the stale config, wipe any stale hook files, then reinstall.
git config --unset-all core.hooksPath 2>/dev/null || true
rm -f .git/hooks/pre-commit .git/hooks/pre-push
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Wait for the db service (bounded — never hang first-run forever), then
# build the schema.
timeout 90 bash -c 'until pg_isready -h db -U arxii -d arxiidev >/dev/null 2>&1; do sleep 1; done' \
  || { echo "db service did not become ready within 90s" >&2; exit 1; }

# --- Stale-database guard (#2977) ------------------------------------------
#
# build_schema.py (invoked below) assumes an empty target - its own
# docstring says so - and its internal idempotency check only asks whether
# arxii_interaction is already partitioned; it does not check schema
# *identity*. Pointed at a database that isn't empty and wasn't built by
# this exact path, it would either collide (DuplicateTable, for tables that
# already exist) or silently graft new tables next to stale ones without
# reconciling the columns of whatever's already there against current model
# state, producing a half-built database that looks fine until something
# queries the wrong half.
#
# "Already built by this path" is judged the same way build_schema.py's own
# `_schema_already_built()` does: arxii_interaction exists and is
# partitioned (relkind = 'p'). That's deliberately narrower than "has any
# arxii_* table at all" - a database with SOME arxii_* tables can still be a
# half-finished `migrate` run sitting next to pre-#2906 debris (observed on
# this exact machine: arxiidev currently holds 100 orphaned `scenes_*`
# tables from before #2906 alongside 421 `arxii_*` tables from an
# interrupted replay, with only 7 of 103 arxii migrations recorded as
# applied), and that state must refuse too, not be waved through just
# because some arxii_* tables happen to exist.
#
# Refuse rather than auto-drop: CLAUDE.md's "preserve the dev database" rule
# exists precisely to stop tooling from destroying a developer's data, so
# the default here is to instruct, not act.
uv run python - <<'PY' || { echo "[post-create] refusing to bootstrap into a stale database (see message above)" >&2; exit 1; }
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

db = settings.DATABASES["default"]

with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
    (table_count,) = cursor.fetchone()
    cursor.execute("SELECT relkind FROM pg_class WHERE relname = 'arxii_interaction'")
    row = cursor.fetchone()

already_built = row is not None and row[0] == "p"
if table_count == 0 or already_built:
    sys.exit(0)

print(
    f"[post-create] target database {db['NAME']!r} is non-empty and was not built by "
    "tools/build_schema.py",
    file=sys.stderr,
)
print(
    "[post-create] (arxii_interaction is not partitioned). Bootstrapping into it would "
    "either collide",
    file=sys.stderr,
)
print(
    "[post-create] with existing tables or silently graft new ones next to stale/incomplete "
    "ones, so",
    file=sys.stderr,
)
print(
    "[post-create] this refuses instead of guessing. Drop and recreate the database, then "
    "re-run this",
    file=sys.stderr,
)
print("[post-create] script (or 'just dc-build'):", file=sys.stderr)
print(
    f"[post-create]   PGPASSWORD={db['PASSWORD']} dropdb -h {db['HOST']} -U {db['USER']} "
    f"{db['NAME']}",
    file=sys.stderr,
)
print(
    f"[post-create]   PGPASSWORD={db['PASSWORD']} createdb -h {db['HOST']} -U {db['USER']} "
    f"{db['NAME']}",
    file=sys.stderr,
)
sys.exit(1)
PY

# Build the schema straight from current model state instead of replaying
# the full migration chain (#2977, continuing ADR-0083 which already moved
# CI and both test tiers onto this path - the devcontainer was the last
# environment still replaying). Measured on this box: ~5m21s versus
# ~27m00s for `arx manage migrate` (#2906/#2977). Migration replay's cost
# is dominated by Django's per-operation ProjectState re-rendering, not
# real DDL, and build_schema.py skips that machinery by disabling
# migrations and creating tables straight from model state, then applying
# the raw partition/composite-FK/materialized-view SQL. It also runs the
# two idempotent seed functions that plain `migrate` never does (ADR-0083's
# trade-offs section): without them, `_get_social_engagement_category()`
# (world/scenes/action_services.py) hard-fails on a missing row the first
# time a scene-action-accept flow runs.
uv run python tools/build_schema.py

# build_schema.py disables migrations entirely while it runs, which means
# it leaves NO django_migrations table at all. Left that way, the next real
# `arx manage migrate` would see nothing recorded as applied and try to
# CREATE TABLE every model from scratch, failing with DuplicateTable.
# `--fake` records every migration in the chain as applied without
# touching the schema (the schema is already there, built above), so the
# ledger matches reality and a later incremental migration - e.g. after
# `git pull` picks up a new migration file - applies normally instead of
# trying to replay history that already happened by another route.
uv run arx manage migrate --fake

# Escape hatch: to exercise the real migration chain locally (e.g.
# reproducing a migration-only bug), point DATABASE_URL at a fresh empty
# database and run `uv run arx manage migrate` directly instead of the two
# commands above. CI's nightly workflow
# (.github/workflows/nightly-migration-replay.yml) is the standing coverage
# for that path; this script no longer exercises it on every container
# create.

# Install required plugins idempotently. claude plugin commands are CLI-
# safe (no Claude Code session needed). The named volume at
# /home/vscode/.claude persists the plugin across container rebuilds,
# so this is fast on second and subsequent runs.
claude plugin marketplace add anthropics/claude-plugins-official 2>/dev/null || true
claude plugin install superpowers@claude-plugins-official 2>/dev/null || true

# Symlink in-repo skills into the user's Claude skills directory so they're
# discoverable by every session. -sfn is idempotent — re-runs cleanly. New
# skills committed to tools/skills/ appear on the next container creation.
# nullglob: if tools/skills/ is empty, the loop body should NOT run with the
# literal pattern (which would create a dangling "*" symlink).
#
# A skill that declares `compatibility: polytoken-only` in its SKILL.md
# frontmatter is Polytoken-exclusive and is SKIPPED here — it would collide
# with a same-named superpowers plugin skill (brainstorming, writing-plans,
# using-git-worktrees) in Claude Code. The plain `compatibility: polytoken`
# marker is additive: such skills are mirrored into Polytoken (below) AND
# symlinked into Claude Code as before. The sync-polytoken-skills step mirrors
# both marker variants into .polytoken/skills/.
mkdir -p /home/vscode/.claude/skills
shopt -s nullglob
for skill in /workspaces/arxii/tools/skills/*/; do
  name=$(basename "$skill")
  if grep -q "^compatibility:[[:space:]]*polytoken-only$" "$skill/SKILL.md" 2>/dev/null; then
    continue
  fi
  ln -sfn "$skill" "/home/vscode/.claude/skills/$name"
done
shopt -u nullglob

# Mirror polytoken-compatible skills into .polytoken/skills/ as real copies so
# the polytoken harness discovers them too (it does not follow symlinks like
# Claude Code does). Selects skills whose SKILL.md declares
# `compatibility: polytoken`. Idempotent; re-run via `just sync-polytoken-skills`.
bash /workspaces/arxii/tools/skills/sync-polytoken-skills.sh
