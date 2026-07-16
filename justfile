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

# Internal: warn when tests run from the 9p-mounted main checkout — Python
# imports over 9p add ~25s to every test invocation vs an ext4 worktree
# under .claude/worktrees/ (the arxii-worktrees named volume).
_fs-warn:
    #!/usr/bin/env bash
    if [ "$(findmnt -no FSTYPE -T . 2>/dev/null)" = "9p" ]; then
        echo "WARNING: this checkout is on a 9p mount; test runs pay ~25s extra here." >&2
        echo "         Prefer an ext4 worktree under .claude/worktrees/ (docs/devcontainer-setup.md)." >&2
    fi

# Run `arx test` with the given args. Thin pass-through; use when you
# don't need to capture output to a file.
#   just test flows --keepdb
#   just test world.combat.tests.test_combat_service --keepdb -v 2
test *args: _fs-warn
    uv run arx test {{args}}

# Inner-loop SQLite tier — fast in-memory DB, excludes @tag("postgres")
# tests that don't work on SQLite. Auto-confirms the destroy-test-DB
# prompt. Auto-enables --parallel when multiple apps are passed (measured
# ~35% faster on 300+ tests); stays serial for a single app/module to
# avoid per-worker DB-clone overhead that regresses small suites.
# Force parallel on a single large app with `just test-fast-par <app>`.
# See CLAUDE.md "Running Tests" for the working/broken per-app set.
#   just test-fast world.missions
#   just test-fast world.checks world.flows
# For apps where the SQLite tier doesn't work (character_sheets, roster,
# magic, scenes, codex, areas, societies) use `just test-parity` instead.
test-fast *args: _fs-warn
    #!/usr/bin/env bash
    set -euo pipefail
    N=$(echo "{{args}}" | wc -w)
    if [ "$N" -gt 1 ]; then
        echo "yes" | uv run arx test --sqlite --parallel --exclude-tag postgres {{args}}
    else
        echo "yes" | uv run arx test --sqlite --exclude-tag postgres {{args}}
    fi

# Force --parallel on the SQLite fast tier, even for a single app.
# Use when a single app has 100+ tests and serial is too slow.
#   just test-fast-par world.conditions
test-fast-par *args: _fs-warn
    echo "yes" | uv run arx test --sqlite --parallel --exclude-tag postgres {{args}}

# Derive the Postgres parity-tier test DB name (test_<dbname>) and its
# host's maintenance-DB URL from src/.env's own DATABASE_URL. A shell-exported
# DATABASE_URL does NOT reach `arx` subcommands (setup_env() reloads
# src/.env with override=True), so every recipe that needs the test DB name
# re-derives it from the file instead of trusting the environment.
# Only supports the plain documented form (postgres://user:pass@host:port/dbname)
# — no query string, no surrounding quotes. Both would silently mis-derive the
# DB name (query lands in it; quotes leak into it), so this validates the
# derived name and fails loudly instead, rather than building a name Postgres
# will accept but nothing else will match.
#   just _testdb-url                 # prints "TESTDB=... MAINT_URL=..." (eval'd by callers)
_testdb-url:
    #!/usr/bin/env bash
    set -euo pipefail
    DBURL=$(grep -E '^DATABASE_URL=' src/.env | head -1 | cut -d= -f2-)
    DBNAME=${DBURL##*/}
    PREFIX=${DBURL%/*}
    if ! [[ "$DBNAME" =~ ^[A-Za-z0-9_]+$ ]]; then
        echo "_testdb-url: src/.env's DATABASE_URL isn't in the supported form." >&2
        echo "  DATABASE_URL=${DBURL}" >&2
        echo "  Derived db name: '${DBNAME}' (must match ^[A-Za-z0-9_]+\$)" >&2
        echo "  Supported form: postgres://user:pass@host:port/dbname" >&2
        echo "  (no query string, no surrounding quotes)" >&2
        exit 1
    fi
    echo "TESTDB=test_${DBNAME}"
    echo "MAINT_URL=${PREFIX}/postgres"
    echo "TESTDB_URL=${PREFIX}/test_${DBNAME}"

# Build (or rebuild) the Postgres parity-tier test database straight from
# current model state — no migration replay. Drops/recreates test_<dbname>
# via psql against the host's `postgres` maintenance DB, then runs
# tools/build_schema.py against it (syncdb + partition/matview SQL + seeds).
# `test-parity`/`regression` call this automatically when the test DB is
# missing, but re-run it by hand (or pass `--rebuild`) after a model change —
# --keepdb reuses whatever schema is already there, it does not detect drift.
#   just build-test-schema
build-test-schema:
    #!/usr/bin/env bash
    set -euo pipefail
    eval "$(just _testdb-url)"
    echo "build-test-schema: rebuilding ${TESTDB}"
    psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"${TESTDB}\";"
    psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${TESTDB}\";"
    DATABASE_URL="$TESTDB_URL" uv run python tools/build_schema.py

# Internal: build the test DB if it doesn't exist yet, if its schema isn't
# actually complete, or if `rebuild` is non-empty. Shared by test-parity and
# regression.
#
# Existence alone isn't enough: a bare `arx test`/`arx test --keepdb` run
# (bypassing this recipe) can make Django itself create test_<dbname> via
# plain syncdb — no partition, no composite FKs, no matviews, no seeds — and
# with --keepdb that broken schema persists. So probe the same signal
# build_schema.py itself uses for its idempotency guard (scenes_interaction
# being partitioned, relkind='p') against the actual test DB, not just
# pg_database existence, and rebuild if it's missing or wrong.
_ensure-testdb rebuild="":
    #!/usr/bin/env bash
    set -euo pipefail
    eval "$(just _testdb-url)"
    EXISTS=$(psql "$MAINT_URL" -tAc "SELECT 1 FROM pg_database WHERE datname='${TESTDB}'")
    SCHEMA_OK=""
    if [ "$EXISTS" = "1" ]; then
        SCHEMA_OK=$(psql "$TESTDB_URL" -tAc \
            "SELECT 1 FROM pg_class WHERE relname='scenes_interaction' AND relkind='p'" \
            2>/dev/null || echo "")
    fi
    if [ -n "{{rebuild}}" ] || [ "$EXISTS" != "1" ] || [ "$SCHEMA_OK" != "1" ]; then
        just build-test-schema
    fi

# CI-parity tier — runs the same Postgres path CI runs, against a pre-built
# test DB (schema from current model state, no migration replay). Builds the
# test DB automatically the first time; pass `--rebuild` to force a rebuild
# after a model change. Always uses --keepdb — the test DB's schema comes
# from `build-test-schema`, not Django's migration-driven create_test_db.
# Serial by default — this tier is expensive enough that going parallel
# should be a deliberate choice, not automatic; pass --parallel yourself if
# you actually want it (e.g. reproducing a CI failure).
# Use before pushing, and for apps that can't run on the SQLite tier.
#   just test-parity world.character_sheets
#   just test-parity --rebuild world.character_sheets   # after a model change
#   just test-parity                              # full suite
test-parity *args: _fs-warn
    #!/usr/bin/env bash
    set -euo pipefail
    REBUILD=""
    ARGS=()
    for tok in {{args}}; do
        if [ "$tok" = "--rebuild" ]; then
            REBUILD="1"
        else
            ARGS+=("$tok")
        fi
    done
    just _ensure-testdb "$REBUILD"
    echo "yes" | uv run arx test --keepdb "${ARGS[@]}"

# Change-impact-aware regression: tests only the apps your branch
# actually touches PLUS apps that import from them (catches the
# "I changed missions, but a stories test uses MissionTemplateFactory"
# case). Falls back to the full suite if any change lands outside
# src/world/<app>/ scope (settings, server config, etc.). Runs on the
# Postgres parity tier — builds the test DB automatically the first time
# (see `build-test-schema`), then always reuses it via --keepdb.
#
# Diffs against origin/main via merge-base. Run `git fetch origin`
# first if you suspect your tracking branch is stale.
#
#   just test-affected
#   just test-affected -v 2             # extra args passed to arx test
test-affected *args: _fs-warn
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
        just _ensure-testdb ""
        echo "yes" | uv run arx test --keepdb --parallel {{args}}
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
    just _ensure-testdb ""
    if [ "$COUNT" -gt 1 ]; then
        echo "yes" | uv run arx test --keepdb --parallel $DOTTED {{args}}
    else
        echo "yes" | uv run arx test --keepdb $DOTTED {{args}}
    fi

# Run the full regression suite against a pre-built Postgres test DB (schema
# from current model state, no migration replay) — matches CI's path exactly,
# including CI's own --keepdb (CI builds the test DB once via
# tools/build_schema.py, then reuses it across the run). Builds the test DB
# automatically the first time; pass `--rebuild` to force a rebuild after a
# model change. Uses --parallel (cpu_count workers). Auto-confirms the
# destroy-test-DB prompt.
#   just regression
#   just regression --rebuild
regression *args: _fs-warn
    #!/usr/bin/env bash
    set -euo pipefail
    REBUILD=""
    ARGS=()
    for tok in {{args}}; do
        if [ "$tok" = "--rebuild" ]; then
            REBUILD="1"
        else
            ARGS+=("$tok")
        fi
    done
    just _ensure-testdb "$REBUILD"
    echo "yes" | uv run arx test --keepdb --parallel "${ARGS[@]}"

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

# Format-then-commit (#756): pre-applies ruff format to the named files so
# the pre-commit format hook can't abort the first pass ("files were
# modified by this hook") and leave HEAD silently unmoved. Hooks still run.
#   just commit "fix(#N): message" src/world/foo/bar.py src/world/foo/baz.py
commit msg +files:
    uv run ruff format {{files}}
    git add {{files}}
    git commit -m "{{msg}}"

# --- Django management -------------------------------------------------------

# Pass-through to `arx manage`. Example:
#   just manage migrate flows
#   just manage makemigrations flows --name add_foo
manage *args:
    uv run arx manage {{args}}

# Apply migrations for all apps.
migrate:
    uv run arx manage migrate

# --- Prod data pull ------------------------------------------------------------

# Fetch the LATEST prod DB dump (via the read-only `dev_reader` Object
# Storage key) and OVERWRITE the local dev DB with it (drop/recreate, then
# migrate) — see infra/README.md "Pull prod data down" for the one-time
# ARXII_DEV_READER_*/ARXII_BACKUPS_* config in src/.env. Explicit
# `confirm=yes` required — mirrors the confirmation-flag gate
# infra/scripts/restore.sh already uses for the same class of destructive
# operation; a bare `just pull-prod` refuses and changes nothing.
#   just pull-prod confirm=yes
pull-prod confirm="no":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{confirm}}" = "yes" ]; then
        bash infra/scripts/pull_prod_db.sh --i-understand-this-overwrites-local
    else
        bash infra/scripts/pull_prod_db.sh
    fi

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

# Run Playwright e2e tests against the Django-served frontend (production
# build). Requires the Evennia server to be running on :4001 (just start).
# The smoke tests (frontend/e2e/smoke.spec.ts etc.) can also run against
# `vite preview` with no backend — use `fe-e2e-frontend` for that mode.
#   just fe-e2e                      # all e2e tests against Django backend
#   just fe-e2e user-journey          # specific spec file
fe-e2e *args:
    cd frontend && npx playwright test --config e2e.backend.config.ts {{args}}

# Run Playwright e2e tests against the Vite preview build (no backend).
# This is the original smoke-test mode — pages render but all API calls fail.
#   just fe-e2e-frontend
#   just fe-e2e-frontend smoke
fe-e2e-frontend *args:
    cd frontend && npx playwright test {{args}}

# Install Playwright's Chromium browser binary. Must be run once before e2e
# tests work. Requires the devcontainer firewall to allowlist cdn.playwright.dev
# (already configured in init-firewall.sh via Azure Front Door ranges).
fe-e2e-install:
    cd frontend && npx playwright install chromium

# Seed a pre-verified test account for e2e / integration testing.
# Creates username 'e2e_test_account' with verified email — idempotent.
#   just seed-test-account
seed-test-account:
    cd src && uv run arx manage seed_test_account

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
# Build fixtures from the private content checkout, then load them.
# Requires CONTENT_REPO_PATH in src/.env (the content repo is never named here).
# If CONTENT_REPO_URL is also set and the checkout doesn't exist, clones it first.
load-content:
    bash tools/ensure_content_repo.sh
    uv run python tools/build_content_fixtures.py --load

# Validate content files + report remaining PLACEHOLDER slots; writes nothing.
check-content:
    uv run python tools/build_content_fixtures.py --check

gen-api-types:
    uv run arx manage spectacular --file schema.json --validate
    pnpm --prefix frontend generate:types
    # openapi-typescript output isn't prettier-formatted; normalize so the diff is
    # just the real schema change, not a whole-file quote/indent reflow.
    pnpm --prefix frontend exec prettier --write src/generated/api.d.ts
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

# Re-copy polytoken-compatible skills (compatibility: polytoken or
# polytoken-only) into .polytoken/skills/ after editing a bridged skill.
# post-create.sh runs this at container creation; this recipe is for picking up
# mid-session edits. Claude Code needs no equivalent — it follows the
# ~/.claude/skills symlinks live (and skips polytoken-only skills there).
sync-polytoken-skills:
    bash tools/skills/sync-polytoken-skills.sh

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
