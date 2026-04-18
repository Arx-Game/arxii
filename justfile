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

# Run `arx test` and mirror combined stdout+stderr to .claude/scratch/<name>.
# Use when output is too big to fit in context and needs reading back.
# <name> must be a bare filename (no slashes, no ..).
#   just test-scratch flows.txt flows --keepdb
#   just test-scratch unified.txt flows.tests.test_emit_unified --keepdb
test-scratch name *args:
    bash .claude/scripts/arx-test-scratch.sh {{name}} {{args}}

# Run the full regression suite (no --keepdb, matches CI).
# Auto-confirms the destroy-test-DB prompt.
#   just regression
regression:
    echo "yes" | uv run arx test

# Run the full regression suite with output captured to .claude/scratch/regression.txt.
regression-scratch:
    bash .claude/scripts/arx-test-scratch.sh regression.txt

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
