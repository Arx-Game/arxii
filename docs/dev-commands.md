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

- `arx test` — Run Evennia tests (Postgres by default; on a fresh environment
  go through `just test-parity` / `just build-test-schema` rather than bare
  `arx test`/`arx test --keepdb` — see the `running-tests` skill)
- `arx test <args>` — Run specific tests with additional arguments
- `arx shell` — Start Evennia Django shell with correct settings
- `arx manage <command>` — Run arbitrary Django management commands
- `arx build` — Build docker images (runs `make build`)

For the full test-tier model (SQLite fast tier vs Postgres parity, `just`
recipes, `--keepdb`), see the `running-tests` skill. `just build-test-schema`
builds the Postgres parity-tier test DB straight from current model state (no
migration replay); `just test-parity` and `just regression` build it
automatically the first time and reuse it via `--keepdb` on every run after —
pass `--rebuild` to either (e.g. `just test-parity --rebuild world.vitals`) to
force a rebuild after a model change. A plain `arx manage migrate` (with no
`build_schema.py` run) leaves the seed functions
(`world/progression/seeds.py`, `world/magic/seeds_soul_tether.py`) uncalled —
a deploy pipeline must invoke them explicitly or lookups like the
`social_engagement` KudosSourceCategory row will be missing.

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

**Always commit with hooks — never `--no-verify`.** `--no-verify` skips this
repo's **custom linters** (`getattr-literal`, `string-literal`, `objectdb-param`,
plus SharedMemoryModel/migration/FilterSet checks) that `ruff`/`ty` do not
cover, so a `--no-verify` commit looks clean locally and then fails CI's
`pre-commit` job — a wasted round trip. It also skips `ty` (the project-wide
type checker) and `ruff-format` (a separate hook from `ruff check`), so running
just `ty check` + `ruff check` by hand afterward is not equivalent to the real
hook set. If a branch was ever built via `--no-verify` commits, run the full
`uv run pre-commit run --all-files` (matches CI's `pre-commit` job) before
push and confirm every hook passes — `uv run pre-commit run --from-ref
origin/main --to-ref HEAD` scopes it to just the branch's changes.

### CI Quality Gates (SonarCloud)

This repo runs **SonarCloud Automatic Analysis** (the zero-config GitHub App —
there is no `SonarSource/*` scanner action in `.github/`). A few
Automatic-Analysis-specific behaviors that differ from a configured scanner:

- **`sonar.issue.ignore.*` in `sonar-project.properties` is a no-op** under
  Automatic Analysis (proven by a PR where scoping a rule off `**/models.py`
  had zero effect). To suppress a rule/issue: deactivate it in the SonarCloud
  UI's Quality Profile, scope it in Analysis Scope, mark it Won't-Fix, or use
  inline `# NOSONAR` (which Automatic Analysis does honor). `sonar.exclusions`
  (not `sonar.issue.ignore.*`) is the one properties-file setting that
  reliably works — it's how this repo excludes test files from analysis.
- **The Quality Gate here fails specifically on "Reliability Rating on New
  Code ≥ A"** — Reliability = Bug-rule findings (e.g. float-equality checks
  flagged as S1244), not code smells (cognitive complexity, S134) or `TODO`
  markers, which annotate but don't fail the gate on their own. Read the check
  summary's *named gate* to see which category is actually failing
  (Reliability=Bugs, Maintainability=Code Smells, Security=Vulnerabilities).
  Fetch precise annotations via the Checks API (`gh api
  repos/<repo>/commits/<sha>/check-runs`, filter for a Sonar check name, follow
  `.output.annotations_url`) — Sonar is an external status check, not a `gh
  run` workflow, so `get-ci-failure.sh`-style tooling reports "no failing run."
- **The separate "SonarCloud Code Analysis" PR check fails on >3% new-code
  duplication** (`new_duplicated_lines_density`), exit 5 from `watch-ci.sh`.
  Test files are fully excluded via `sonar.exclusions`, so a new-code
  duplication failure is always in **source**, never tests — don't touch
  tests to fix it. The recurring trigger is a cluster of thin, near-identical
  wrapper functions (e.g. repetitive `Action` classes each doing
  `try: service(...); except DomainError: return failure`); fix by
  extracting a shared helper. Sonar's mechanical duplication check doesn't
  grade semantic justification, so even duplication a human reviewer calls
  "reasonable" still fails the gate.
- **A backend-only model retype (e.g. int→enum) can trip both the duplication
  gate indirectly and, separately, the frontend `api-types-drift`/build gates**
  (see "Generated API Schema" in `django_notes.md`) — regenerating the
  *generated* frontend types isn't sufficient if a **hand-written** frontend
  type shadows the changed field; `tsc --noEmit` (project-check mode) does not
  catch that mismatch, only `pnpm build` (`tsc -b`, the mode CI actually runs)
  does. Always verify a frontend TS fix with the literal CI command.
- **`gh pr checks`/`statusCheckRollup` can report a FAILING check for a commit
  that's already fixed, immediately after pushing** — it's showing the
  last-completed conclusion for that check *name*, not necessarily tied to
  current HEAD, while the new run is still queued/in-progress. Cross-check
  `gh run list --branch <branch> --json databaseId,status,headSha` for a run
  whose `headSha` matches `git rev-parse HEAD` before trusting a poller.

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
