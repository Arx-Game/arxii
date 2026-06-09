# Development Commands Reference

Command reference for working on Arx II. The load-bearing *rules* live in
`CLAUDE.md`; this file is the lookup table for the commands themselves.

> All `arx` commands require the venv to be activated, or must be prefixed with
> `uv run` (e.g. `uv run arx test`). Use `uv run arx` when unsure whether the
> venv is active.

## Development Setup

- `uv sync` — Install Python dependencies
- `uv venv` — Create virtual environment
- `pre-commit install` — Install pre-commit hooks
- **Sandboxed devcontainer** (for `--dangerously-skip-permissions`): see `docs/devcontainer-setup.md`

## Common Development Commands

- `arx test` — Run Evennia tests (run `arx manage migrate` first if fresh environment)
- `arx test <args>` — Run specific tests with additional arguments
- `arx shell` — Start Evennia Django shell with correct settings
- `arx manage <command>` — Run arbitrary Django management commands
- `arx build` — Build docker images (runs `make build`)

For the full test-tier model (SQLite fast tier vs Postgres parity, `just`
recipes, `--keepdb`), see the `running-tests` skill.

## Server Management

- `arx start` — Start the Evennia server (**PREFERRED** for running the server)
- `arx stop` — Stop the Evennia server
- `arx stop --hard` — Force-kill all Evennia processes (use when server hangs)
- `arx reload` — Reload the Evennia server (picks up code changes)
- `arx ngrok` — Start ngrok tunnel and auto-update .env for manual testing
  - Updates `src/.env` with `FRONTEND_URL` and `CSRF_TRUSTED_ORIGINS`
  - Updates `frontend/.env` with `VITE_ALLOWED_HOSTS` (for Vite dev server)
  - `arx ngrok --status` — Check if ngrok is running and show current URL
  - `arx ngrok --force` — Kill existing ngrok and restart with new tunnel
  - **Note:** ngrok URLs are ephemeral and dev-only. `frontend/.env` is gitignored
    to prevent committing ngrok domains.

**Always use `arx start` to run the server, NOT `arx manage runserver`.** `arx
start` properly starts the Evennia portal and server processes; `runserver` is a
Django-only command that doesn't fully initialize Evennia.

## Linting and Formatting

- `ruff check .` — Run Python linting (import sorting, flake8 rules, and more)
- `ruff check . --fix` — Auto-fix Python linting issues where possible
- `ruff format .` — Format Python code (replaces black/isort, line length 100)
- `pre-commit run --all-files` — Run all pre-commit hooks (uses ruff)

## Frontend Development (in `frontend/`)

- `pnpm dev` — Start Vite development server with Django API proxy
- `pnpm build` — Build production assets to `src/web/static/dist/`
- `pnpm lint` — Run ESLint on TypeScript/React files
- `pnpm lint:fix` — Run ESLint with auto-fix
- `pnpm format` — Format code with Prettier
- `pnpm typecheck` — Run TypeScript type checking
- `just gen-api-types` — Regenerate OpenAPI schema (`src/schema.json`) and frontend
  TypeScript API types (`frontend/src/generated/api.d.ts`)

### `pnpm build` must always chain `collectstatic`

`pnpm build` writes hashed assets to `src/web/static/dist/`. Django serves static
files from `src/server/.static/`, populated by `arx manage collectstatic`. Without
that step, the freshly-built HTML points at hashes the server 404s on — symptom is
a blank page with console 404s for `index-*.js` / `index-*.css`.

`frontend/package.json` has a `postbuild` script that auto-chains `collectstatic
--noinput` after every `pnpm build` (covers `just fe-build`, CI, etc.). If you see
blank-page-with-404 symptoms, check whether the postbuild ran (the `pnpm build`
output should end with a `static files copied to .../src/server/.static` line). If
someone disabled the postbuild or runs `tsc -b && vite build` directly bypassing
pnpm scripts, reinstate the chain.

## Integration Testing

- `arx integration-test` — Automated integration test environment (highly automated!)
  - Requires `ALLOW_INTEGRATION_TESTS=true` in `src/.env` (safety check)
  - See `src/integration_tests/QUICKSTART.md` for usage guide
  - Automatically: starts ngrok, Django, frontend, registers test account, fetches
    verification email
  - Human verification: click verification link, confirm UI, test login
  - Press Ctrl+C to cleanup and restore everything
