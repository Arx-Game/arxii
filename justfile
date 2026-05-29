#
# arx-ii task runner
#
# Common developer tasks wrapped as named recipes so they can be
# invoked via a single whitelist rule (Bash(just:*)) instead of
# accumulating per-path permission approvals for raw bash/python scripts.
#
# List recipes:   just
# Run one:        just <recipe> [args...]
#

# Default recipe — print the list.
default:
    @just --list --unsorted

# --- Testing -----------------------------------------------------------------

# Run `arx test` with the given args. Thin pass-through; use when you
# don't need to capture output to a file.
#   just test flows --keepdb
#   just test world.combat.tests.test_combat_service --keepdb -v 2
test *args:
    uv run arx test {{args}}

# Inner-loop SQLite tier — fast in-memory DB, excludes @tag("postgres")
# tests that don't work on SQLite. Auto-confirms the destroy-test-DB
# prompt. Serial by default: --parallel REGRESSES small per-app suites
# (per-worker DB-clone overhead > parallelism gain). See CLAUDE.md
# "Running Tests" for the working/broken per-app set.
#   just test-fast world.missions
#   just test-fast world.checks world.flows
# For apps where the SQLite tier doesn't work (character_sheets, roster,
# magic, scenes, codex, areas, societies) use `just test-parity` instead.
test-fast *args:
    echo "yes" | uv run arx test --sqlite --exclude-tag postgres {{args}}

# CI-parity tier — runs the same Postgres path CI runs, in parallel.
# Use before pushing, and for apps that can't run on the SQLite tier.
#   just test-parity world.character_sheets
#   just test-parity                              # full suite, ~30+ min
test-parity *args:
    echo "yes" | uv run arx test --parallel {{args}}

# Change-impact-aware regression: tests only the apps your branch
# actually touches PLUS apps that import from them (catches the
# "I changed missions, but a stories test uses MissionTemplateFactory"
# case). Falls back to the full suite if any change lands outside
# src/world/<app>/ scope (settings, server config, etc.).
#
# Diffs against origin/main via merge-base. Run `git fetch origin`
# first if you suspect your tracking branch is stale.
#
#   just test-affected
#   just test-affected --keepdb         # extra args passed to arx test
test-affected *args:
    #!/usr/bin/env bash
    set -euo pipefail
    BASE=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main)
    CHANGED=$(git diff --name-only "$BASE" HEAD -- 'src/**/*.py')
    if [ -z "$CHANGED" ]; then
        echo "test-affected: no .py changes vs origin/main."
        echo "Use 'just regression' for the full suite, or 'just test-fast <app>' for one."
        exit 0
    fi
    OUTSIDE=$(echo "$CHANGED" | grep -vE '^src/world/[^/]+/' || true)
    if [ -n "$OUTSIDE" ]; then
        echo "test-affected: changes outside src/world/<app>/ — running full regression:"
        echo "$OUTSIDE" | sed 's/^/  /'
        echo "yes" | uv run arx test --parallel {{args}}
        exit 0
    fi
    CHANGED_APPS=$(echo "$CHANGED" | sed -E 's|^src/world/([^/]+)/.*|\1|' | sort -u)
    ALL_APPS="$CHANGED_APPS"
    for app in $CHANGED_APPS; do
        DEPS=$(grep -rlE "from world\.${app}([.]| import)" src/world/ --include='*.py' 2>/dev/null \
               | sed -E 's|^src/world/([^/]+)/.*|\1|' | sort -u || true)
        ALL_APPS="${ALL_APPS}"$'\n'"${DEPS}"
    done
    APPS=$(echo "$ALL_APPS" | sort -u | grep -v '^$')
    DOTTED=$(echo "$APPS" | sed 's|^|world.|' | tr '\n' ' ')
    COUNT=$(echo "$APPS" | wc -l)
    echo "test-affected: $COUNT app(s) — $(echo $APPS | tr '\n' ' ')"
    if [ "$COUNT" -gt 1 ]; then
        echo "yes" | uv run arx test --parallel $DOTTED {{args}}
    else
        echo "yes" | uv run arx test $DOTTED {{args}}
    fi

# Run the full regression suite (no --keepdb, matches CI's fresh-DB behavior).
# Uses --parallel (cpu_count workers) — local wall-clock is multiple-x faster
# than serial; behavior matches CI in every other way (no --keepdb, full suite,
# Postgres). Auto-confirms the destroy-test-DB prompt.
#   just regression
regression:
    echo "yes" | uv run arx test --parallel

# --- Lint / format -----------------------------------------------------------

# Run ruff check.
lint *args:
    uv run ruff check {{args}}

# Run ruff check --fix.
lint-fix *args:
    uv run ruff check --fix {{args}}

# Run ruff format.
fmt *args:
    uv run ruff format {{args}}

# Run all pre-commit hooks on every file.
precommit:
    uv run pre-commit run --all-files

# --- Django management -------------------------------------------------------

# Pass-through to `arx manage`. Example:
#   just manage migrate flows
#   just manage makemigrations flows --name add_foo
manage *args:
    uv run arx manage {{args}}

# Apply migrations for all apps.
migrate:
    uv run arx manage migrate

# --- Server ------------------------------------------------------------------

start:
    uv run arx start

stop:
    uv run arx stop

reload:
    uv run arx reload

# --- Frontend ----------------------------------------------------------------

fe-dev:
    cd frontend && pnpm dev

fe-build:
    cd frontend && pnpm build

fe-typecheck:
    cd frontend && pnpm typecheck

fe-lint *args:
    cd frontend && pnpm lint {{args}}

# Run Vitest unit tests. Pass a file/glob to run a subset.
#   just fe-test
#   just fe-test src/rituals/__tests__/fields.test.tsx
fe-test *args:
    cd frontend && pnpm test --run {{args}}

# --- Cache / scratch ---------------------------------------------------------

# Delete all Python bytecode caches under src/.
# Useful when stale .pyc files cause import errors (e.g. after renaming/moving
# modules). Safe to run at any time; Python will recompile on next import.
#   just clean-pyc
clean-pyc:
    uv run python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('src').rglob('__pycache__')]"
    @echo "clean-pyc: bytecode caches removed."

# --- API codegen -------------------------------------------------------------

# Regenerate the OpenAPI schema + frontend TypeScript API types.
# Runs drf-spectacular to write src/schema.json, then runs
# openapi-typescript (via pnpm) to write frontend/src/generated/api.d.ts.
# Either step's failure aborts the pipeline.
# Note: `arx manage` chdirs to src/ before invoking evennia, so the --file
# path is relative to src/ (i.e. schema.json lands at src/schema.json).
#   just gen-api-types
gen-api-types:
    uv run arx manage spectacular --file schema.json --validate
    pnpm --prefix frontend generate:types
    @echo "gen-api-types: schema regenerated and frontend types updated."

# --- Devcontainer (host-side; run these OUTSIDE the container) ---------------

# Requires the devcontainer CLI: npm i -g @devcontainers/cli
# These wrap the devcontainer CLI (NOT raw docker compose) so the
# claude-code feature install and postCreate/postStart hooks actually run.
# Raw `docker compose up` would give an unprovisioned container.
_dc := ".devcontainer/docker-compose.yml"

# Build + start the stack and run all devcontainer setup hooks
dc-up:
    bash .devcontainer/sync-env.sh
    devcontainer up --workspace-folder .

# Full rebuild (no cache) and re-run setup
dc-build:
    bash .devcontainer/sync-env.sh
    devcontainer up --workspace-folder . --build-no-cache --remove-existing-container

# Open a shell INSIDE the app container (this is where you run `claude`)
dc-shell:
    devcontainer exec --workspace-folder . bash

# --- Demo content -------------------------------------------------------------

# Spawn a playable combat scenario via the PlayableCombatScenarioFactory.
# Materializes Scene + DECLARING encounter + 2 PCs (with sheets/vitals/anima/
# techniques/threads/resonance) + NPC opponent + active Clash. Prints the
# entity IDs so a logged-in dev user can navigate to /scenes/<scene_id>/combat
# in the frontend.
#
# Note: this is a developer/QA tool — it creates fresh entities each run, not
# tied to any existing dev-user account. Full dev-user provisioning is a
# follow-up.
demo-combat:
    uv run arx manage shell -c "from world.combat.factories import PlayableCombatScenarioFactory; s = PlayableCombatScenarioFactory.create(); print(f'\\nScene: /scenes/{s.scene.pk}/combat\\nEncounter: {s.encounter.pk}\\nPCs: {[p.pk for p in s.participants]}\\nOpponent: {s.opponent.pk}\\nClash: {s.clash.pk}')"

# Run the test suite inside the container
dc-test *args:
    devcontainer exec --workspace-folder . bash -lc "uv run arx test {{args}}"

# Copy the Windows host's per-project Claude memory dir into the running devcontainer.
# Fresh devcontainers start with empty in-container memory; this recipe bridges the
# gap so Claude has continuity across container rebuilds.
#
# NOTE: This recipe runs on the Windows host (Git Bash), not inside the
# container. Mac/Linux contributors can ignore it.
#
# Hardcodes container name (arxii-devcontainer-app-1) — matches the compose
# project name; fragile if anyone renames the compose stack.
dc-sync-memory:
    #!/usr/bin/env bash
    set -euo pipefail
    WIN_PROJ=$(pwd -W | sed 's|/|\\|g; s|\\|/|g; s|:||; s|^|/|')
    SRC="$USERPROFILE/.claude/projects/${WIN_PROJ//\//-}/memory"
    DEST="/home/vscode/.claude/projects/-workspaces-arxii/memory"
    if [ ! -d "$SRC" ]; then
        echo "No memory dir found at $SRC — nothing to sync." >&2
        exit 1
    fi
    MSYS_NO_PATHCONV=1 docker cp "$SRC/." "arxii-devcontainer-app-1:$DEST/"
    echo "Synced $(ls "$SRC" | wc -l) file(s) to container:$DEST"

# Stop the stack (named db volume is preserved by the pinned project name)
dc-down:
    docker compose -p arxii-devcontainer -f {{_dc}} down
