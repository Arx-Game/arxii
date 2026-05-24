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

# Run the full regression suite (no --keepdb, matches CI).
# Auto-confirms the destroy-test-DB prompt.
#   just regression
regression:
    echo "yes" | uv run arx test

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

# Run the test suite inside the container
dc-test *args:
    devcontainer exec --workspace-folder . bash -lc "uv run arx test {{args}}"

# Stop the stack (named db volume is preserved by the pinned project name)
dc-down:
    docker compose -p arxii-devcontainer -f {{_dc}} down
