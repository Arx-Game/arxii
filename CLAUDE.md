# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent Communication

**Questions in user-facing text must be unambiguous.** If you write a sentence that ends in `?` in text the user sees, it must either:
- Be issued through `AskUserQuestion` (the answer is required to proceed), OR
- Be restated as a statement when it's rhetorical self-direction (e.g., "Checking whether the skill expects a reviewer dispatch step." — not "Does the skill expect a reviewer dispatch step?").

Ambiguous "?" sentences force the user to guess whether they're being asked to respond. When in doubt, no `?` in user-facing text outside of `AskUserQuestion`.

<!-- TEMP HARNESS-BUNDLING-WORKAROUND — remove when GH #647 is resolved -->
**[TEMP] Ground before you act — load the `grounding-before-action` skill at session start.** Claude Code 2.1.158 has a regression: a tool result emitted in the **same message** as the call it depends on is invisible at compose time, so the model confabulates what it returned and acts on the fiction (caused real erroneous GitHub edits; see `tools/skills/grounding-before-action/`). Until it's patched: never co-emit `AskUserQuestion` (or any sentence stating what a tool returned) with the tool calls it depends on — emit calls, end the turn, observe, then act. **Emit `AskUserQuestion` solo** (only tool call in its message — this keeps the picker working), and **echo the chosen answer back in plain text before any irreversible action** so an auto-answer/confabulation is caught before it does damage. Verify issue number↔title before any mutation. This is a **temporary** workaround tracked in **#647** (grep `HARNESS-BUNDLING-WORKAROUND`); delete it when the harness is fixed.

## Git Workflow

> For end-to-end issue → merged-PR work, see the `issue-to-merged-pr` skill at `tools/skills/issue-to-merged-pr/`. It handles branch creation, PR opening, CI watching, and post-merge cleanup. The conventions below still apply; the skill is built on top of them.

### Spec review happens on the issue (not in the repo)

New feature specs live in the **GitHub issue body** (between `<!-- spec:start -->` and `<!-- spec:end -->` markers) rather than as committed `docs/superpowers/` files. (Specs predating this convention still live in `docs/superpowers/`; they're being triaged into `docs/` or issues — see #660.) The `issue-to-merged-pr` flow drafts the spec onto the issue, flags the team, then **stops** until a human org member approves it. Lanes are tracked by **labels** (the source of truth):

- `status:spec-draft` — agent is writing the spec into the issue body
- `status:spec-review` — spec posted; awaiting approval (agent has exited)
- `spec:approved` — **member-only gate.** On our public repo, GitHub lets only Triage+ org members apply labels, so this label *is* the authorization boundary. **Agents MUST NEVER apply `spec:approved`** — they hold the maintainer PAT but must self-restrain and only poll for it.
- `status:implementing` — approved; building toward a PR (normal code review)

Comments are for discussion only — never gate on them (anyone can comment on a public issue). The `superpowers:writing-plans` output is **ephemeral** (worktree-only, never committed).

**IMPORTANT: Never work directly on main.** Always create a feature branch before making changes:

```bash
git checkout -b feature-name
```

This prevents confusion when PRs are squash-merged and keeps main clean. After a PR is merged, delete the local branch and pull main:

```bash
git checkout main && git pull && git branch -D feature-name
```

**GitHub CLI usage:** Use `gh` (and the standard PR-creation recipe in your system prompt) to open PRs for completed work. The `issue-to-merged-pr` skill at `tools/skills/issue-to-merged-pr/` is the preferred path for end-to-end issue → merged-PR work because its scripts wrap `gh` with auditable, dry-run-able contracts; outside that workflow, plain `gh pr create` is fine. Branch protection on `main` plus the maintainer's PAT scope provide the safety rails. Read-only `gh api` calls (listing alerts, fetching PR state, etc.) are also fine when needed. **See the `github-operations` skill (`tools/skills/github-operations/`) for `gh` discipline:** take the new issue/PR number from the URL the create command returns (never compute `N+1` — issues and PRs share one counter), verify number↔title before any mutation, and keep issue/PR writes one-per-message.

**No `cd &&` compound commands:** Never combine `cd` with other commands using `&&` (e.g., `cd /path && git status`). On Windows, Claude Code flags all `cd && <command>` compounds for manual approval as a bare-repository-attack mitigation, which blocks automated workflows. Instead:
- For git: use `git -C /path/to/repo <command>` (e.g., `git -C /c/Users/apost/PycharmProjects/arxii status`)
- For other tools: use absolute paths or the tool's own directory flag
- The working directory is already the repo root in most sessions, so `cd` is rarely needed anyway

This rule exists as a workaround for a Claude Code permission-check behavior on Windows (as of mid-2026). If future releases stop flagging `cd && git` compounds, this rule can be relaxed.

## Essential Commands

### Development Setup
- `uv sync` - Install Python dependencies
- `uv venv` - Create virtual environment
- `pre-commit install` - Install pre-commit hooks
- **Sandboxed devcontainer** (for `--dangerously-skip-permissions`): see `docs/devcontainer-setup.md`

### Common Development Commands
All `arx` commands below require the venv to be activated, or must be prefixed with `uv run` (e.g., `uv run arx test`). Use `uv run arx` when unsure whether the venv is active.

- `arx test` - Run Evennia tests (run `arx manage migrate` first if fresh environment)
- `arx test <args>` - Run specific tests with additional arguments
- `arx shell` - Start Evennia Django shell with correct settings
- `arx manage <command>` - Run arbitrary Django management commands
- `arx build` - Build docker images (runs `make build`)

### Server Management
- `arx start` - Start the Evennia server (PREFERRED for running the server)
- `arx stop` - Stop the Evennia server
- `arx stop --hard` - Force-kill all Evennia processes (use when server hangs)
- `arx reload` - Reload the Evennia server (picks up code changes)
- `arx ngrok` - Start ngrok tunnel and auto-update .env for manual testing
  - Automatically updates `src/.env` with `FRONTEND_URL` and `CSRF_TRUSTED_ORIGINS`
  - Automatically updates `frontend/.env` with `VITE_ALLOWED_HOSTS` (for Vite dev server)
  - `arx ngrok --status` - Check if ngrok is running and show current URL
  - `arx ngrok --force` - Kill existing ngrok and restart with new tunnel
  - **Note:** ngrok URLs are ephemeral and dev-only. `frontend/.env` is gitignored to prevent committing ngrok domains.

**IMPORTANT:** Always use `arx start` to run the server, NOT `arx manage runserver`. The `arx start` command properly starts the Evennia server with portal and server processes, while `runserver` is a Django-only command that doesn't fully initialize Evennia.

### Linting and Formatting
- `ruff check .` - Run Python linting (includes import sorting, flake8 rules, and more)
- `ruff check . --fix` - Auto-fix Python linting issues where possible
- `ruff format .` - Format Python code (replaces black/isort, configured for line length 100)
- `pre-commit run --all-files` - Run all pre-commit hooks (now uses ruff)

### Frontend Development (in frontend/ directory)
- `pnpm dev` - Start Vite development server with Django API proxy
- `pnpm build` - Build production assets to `src/web/static/dist/`
- `pnpm lint` - Run ESLint on TypeScript/React files
- `pnpm lint:fix` - Run ESLint with auto-fix
- `pnpm format` - Format code with Prettier
- `pnpm typecheck` - Run TypeScript type checking
- `just gen-api-types` - Regenerate OpenAPI schema (`src/schema.json`) and frontend TypeScript API types (`frontend/src/generated/api.d.ts`)

**Important: `pnpm build` must always chain `collectstatic`.** `pnpm build`
writes hashed assets to `src/web/static/dist/`. Django serves static files
from `src/server/.static/`, populated by `arx manage collectstatic`. Without
that step, the freshly-built HTML points at hashes the server 404s on —
symptom is a blank page with console 404s for `index-*.js` / `index-*.css`.

`frontend/package.json` has a `postbuild` script that auto-chains
`collectstatic --noinput` after every `pnpm build` (covers `just fe-build`,
CI, etc.). If you ever see blank-page-with-404 symptoms, check whether the
postbuild ran (the `pnpm build` output should end with a
`static files copied to .../src/server/.static` line). If someone disabled
the postbuild or runs `tsc -b && vite build` directly bypassing pnpm
scripts, reinstate the chain.

### Integration Testing
- `arx integration-test` - Automated integration test environment (highly automated!)
  - Requires `ALLOW_INTEGRATION_TESTS=true` in `src/.env` (safety check)
  - See `src/integration_tests/QUICKSTART.md` for usage guide
  - Automatically: starts ngrok, Django, frontend, registers test account, fetches verification email
  - Human verification: click verification link, confirm UI, test login
  - Press Ctrl+C to cleanup and restore everything

## Architecture Overview

### Core Structure
Arx II is a **web-first multiplayer RPG** built on the Evennia framework. The React frontend is the primary game interface - all features should be designed for modern web UX (interactive components, visual feedback, responsive layouts). Telnet/MUD client access is a secondary compatibility goal, not the design target. Do not design features around text-command-and-response patterns; design for the web and let telnet support follow where it can.

The backend uses a sophisticated flow-based command system:

1. **Commands** (`src/commands/`) - Simple command classes that only interpret input and delegate to dispatchers
2. **Dispatchers** - Parse text using regex and call handlers with resolved objects
3. **Handlers** (`src/commands/handlers/`) - Perform permission checks and trigger flows
4. **Flows** (`src/flows/`) - Core game logic engine that handles state changes and messaging
5. **Triggers** - React to events and can modify flow execution

### Key Components

#### Flow System (`src/flows/`)
- **Flow Engine** - Executes sequences of steps based on triggers and events
- **Object States** - Character, room, exit states that implement permission methods (`can_move`, `can_open`, etc.)
- **Service Functions** - Handle communication, movement, perception
- **Scene Data Manager** - Manages temporary scene state

#### Command Architecture
Commands follow the pattern: Input → Dispatcher → Handler → Flow → Service Function
- Commands are intentionally simple and only glue components together
- All game logic lives in flows, triggers, or service functions
- Permission checks delegate to object states which emit intent events

#### Evennia Integration
- Built on Evennia framework with Django backend
- Custom typeclasses in `src/typeclasses/`
- Server configuration in `src/server/conf/`
- Web interface components in `src/web/`

### Project Structure
- `src/cli/arx.py` - CLI entry point with typer-based commands
- `src/flows/` - Flow engine and game logic
- `src/commands/` - Command system with dispatchers and handlers
- `src/typeclasses/` - Evennia object definitions
- `src/server/` - Evennia server configuration
- `docs/` - Documentation including command system overview

### Development Environment
- Python 3.13+ managed by mise
- Node.js v20 for web assets
- uv for dependency management
- Environment file: `src/.env`
- Working directory should be `src/` for Django commands

## Roadmap

**Before starting work on a new system or feature, consult `docs/roadmap/ROADMAP.md`.**

The roadmap provides:
- Overview of all game systems and their current status
- Design principles that apply to every system
- Key design decisions and constraints for each domain
- What exists vs. what's still needed for MVP

Individual domain stubs (e.g., `docs/roadmap/combat.md`) contain detailed design points,
what's already built, and what's needed for MVP.

## Systems Index - IMPORTANT

**Before implementing features that touch multiple systems, consult `docs/systems/INDEX.md`.**

The systems index provides:
- Quick reference of all existing systems, their models, and key functions
- Integration points showing how systems connect
- Common queries and code patterns to reuse

This prevents reinventing existing functionality. For example, before building something that needs character traits, magic, or progression - check the index to find existing models and helper functions.

Individual system docs (e.g., `docs/systems/magic.md`) contain:
- Complete model listings with field descriptions
- Copy-pasteable code examples for common operations
- API endpoint references
- Frontend integration details

## Anti-Reinvention Pass — REQUIRED for feature design

**Every feature-design workflow MUST include an explicit "no reinventing the wheel" pass before the spec is finalized.** This is not optional. Sprawl from parallel components/dataclasses/enums/helpers is the most expensive failure mode in this codebase.

**Use the `verify-against-code` skill** (`tools/skills/verify-against-code/`) for this pass — it carries the labeling procedure, the ledger format, and the recurring-traps list. The core rule: **existing code is the source of truth; docs are stale hints.** Repeatedly in this repo, trusting a doc's "not built" / "already does X" claim over the code has caused near-rebuilds of systems that already exist (or designs against fields that don't).

When designing a new feature or bundled PR:

1. After drafting the design sections but **before** committing the spec, scan the codebase for every proposed new surface — component, dataclass, enum, Django model, helper, UI primitive, hook, serializer.
2. **Verify against code, not docs.** For each proposed new thing, read the actual definition AND find a live caller, then label it exactly one of: **`[BUILT & WIRED]`** (exists with a live caller — quote it `file:line`; reuse, don't build), **`[BUILT, NOT WIRED]`** (exists but no live consumer — wire/extend, don't duplicate), or **`[ABSENT]`** (grep + read confirm it's genuinely new). A name match, a doc claim, or an Explore-agent summary is never enough for a label — confirm with code.
3. **Treat `docs/systems/INDEX.md`, `docs/systems/MODEL_MAP.md`, architecture/roadmap docs, and prior agent summaries as HINTS that may be stale** — use them to find where to look, never as proof of what exists or doesn't. When a doc turns out to be wrong, **correct it at the source as part of this work** so it stops misleading the next person.
4. Consolidate: drop or rename newly-proposed surfaces that overlap with existing ones. Prefer **reuse-with-extension** over **build-new**.
5. Present the consolidations to the user for ratification before committing the updated spec.

Recurring traps to watch for:
- Inventing a new dataclass that mirrors an existing `AvailableX` / `XAvailability` / `XDescriptor`.
- Adding a new TextChoices that overlaps with an existing one along a different axis (check whether the axes are genuinely orthogonal before adding).
- Building a UI component when a shadcn/radix primitive in `frontend/src/components/ui/` already covers it.
- Adding a method to a base class when there's already a class field that captures the same data.
- Adding boolean fields that duplicate information already derivable from another field (e.g., `is_targeted` when `target_spec is not None` already says it).

### Model Map

**For cross-app FK relationships and service function signatures, consult `docs/systems/MODEL_MAP.md`.**

This is auto-generated via `uv run python tools/introspect_models.py` and contains:
- Every model's foreign keys and what points to it (reverse relations)
- Service function signatures with type hints
- Regenerate after major model changes to keep it current

## Critical Evennia Migration Quirks

**Use `arx manage makemigrations`** (a custom command that prevents phantom Evennia-library migrations). For the makemigrations solution, the Evennia integration strategy (use Evennia models, extend via `evennia_extensions`, no attributes, item-data routing), and the new-app migration strategy: see `docs/evennia-quirks.md`.

### Database Design Principles
- **No JSON Fields**: Avoid JSONField - each setting/configuration should be a proper column with validation and indexing
- **Proper Schema**: Use foreign keys, proper data types, and database constraints
- **Queryable Data**: All data should be easily queryable with standard Django ORM
- **Avoid direct FKs to ObjectDB**: Evennia's ObjectDB is a generic base for all game objects (characters, rooms, exits, items). FKs to ObjectDB are almost always too broad — use a more specific model: Persona for IC identities, RosterEntry for played characters, CharacterSheet for character data, RoomProfile for rooms. Only use ObjectDB when the FK genuinely needs to point to any object type (e.g., Evennia internals). When you see an ObjectDB FK, ask: "could this be a vase of flowers?" **The same rule applies to service-function parameter annotations** — enforced by `tools/lint_objectdb_param.py` via the `objectdb-param` pre-commit hook. Use `# noqa: OBJECTDB_PARAM — <justification>` when ObjectDB is genuinely the right type. The lint scope expands one app at a time (see the `files:` regex in `.pre-commit-config.yaml`); new code in the in-scope modules must pass clean.

### Running Tests

**Always use `arx test` or its `just` wrappers** — never `uv run python -m`, `python manage.py test`, or sourcing venvs. Tests run in two tiers: SQLite for the inner loop (`just test-fast <app>`), Postgres for parity (`just test-parity <app>` / `just regression` — what CI runs). Run the full suite without `--keepdb` before pushing. Prefer `just <recipe>` over raw `bash`/`python`.

**For the full two-tier model, the per-app SQLite/PG tier table, all the recipes, `@tag("postgres")` decisions, the `--keepdb` pitfall, and the "never rely on Evennia defaults in service functions" rule: see the `running-tests` skill.**

### Proactive Quality Checks

When editing Python files:
- Run `arx test <app>` after making changes to that app (don't wait to be asked)
- Run `ruff check <file>` on changed files before moving on

Dead code removal (be careful - this is active development):
- Check for TODO/FIXME comments before removing anything that looks unused
- Stub methods, empty implementations, and unused imports may be intentional placeholders
- When in doubt, ASK before removing - false positives waste more time than leaving a stub
- Only remove code that is clearly obsolete (old implementations replaced by new ones)

When editing TypeScript files:
- Run `pnpm typecheck` after making changes
- Run `pnpm lint` on changed files

When completing a task:
- Run relevant tests before claiming "done"
- Verify the change works as expected

### Completing a Unit of Work

When a feature branch or logical unit of work is finished:
- **Update the roadmap** — mark completed phases/items in the relevant `docs/roadmap/*.md` file. Document what was built, not just that it's done.
- **Run full regression tests** — all affected test suites, not just the new tests
- **Run the suite once without `--keepdb`** before pushing — this matches CI's fresh-DB behavior and catches bugs that depend on preserved test DB state (especially Evennia setup objects like Limbo). See the `running-tests` skill for why this matters.

### Code Quality Standards

Core always-on rules (the full list lives in `django_notes.md`):
- **No relative imports** — absolute only (`from world.roster.models import Roster`, not `from .models import ...`).
- **No Django signals** — use explicit, testable service-function calls.
- **No data migrations pre-production** — schema migrations only; no `RunPython` backfills (no meaningful rows yet).
- **Preserve the dev database** — never drop/flush/destroy it except in dire circumstances.
- **PostgreSQL only (production)** — use PG features directly (CTEs, materialized views, `DISTINCT ON`, JSONB); no DB-agnostic workarounds.
- **100-char line limit.** Use `.env` for configurable settings.

**For the full Code Quality Standards (type annotations + `ty`, model-instance preference, avoid dict returns, separate `types.py`, `Meta.ordering` policy, inheritance-over-protocols, service-functions-use-instances, denormalization rules, `TextChoices` in `constants.py`, no-queries-in-loops, no-management-commands, no-backwards-compat, the `# noqa` suppression policy + custom-linter tokens incl. `OBJECTDB_PARAM`, SharedMemoryModel/`Prefetch`/`cached_property`, constants-over-string-literals, FilterSets-in-views): see "## Code Quality Standards" in `django_notes.md`.**

### Django-Specific Guidelines
**For all Django development (models, views, APIs, tests), follow the guidelines in `django_notes.md`.**

Key Django requirements:
- Use Django TextChoices/IntegerChoices for model field choices
- All ViewSets must have filters, pagination, and permission classes
- Use FactoryBoy for all test data with `setUpTestData` for performance
- Focus tests on application logic, not Django built-in functionality

**FactoryBoy `django_get_or_create` gotcha** (it silently drops non-lookup kwargs when the row pre-exists) + the `_create` override that fixes it: see "## FactoryBoy `django_get_or_create` Gotcha" in `django_notes.md`.

### ViewSet & API Design

ViewSets must have filters, pagination, and permission classes. For the design rules (separate ViewSet per related-model CRUD, no implicit first-item selection, prefer Django/DRF helpers, never `str(exc)` in responses, validation-in-serializers, permissions-in-permission-classes): see "## ViewSet & API Design (Standards)" in `django_notes.md`.

### Migration Management for New Apps
**When working on a new app, avoid multiple migrations during development** — see `docs/evennia-quirks.md` (and `django_notes.md` for the in-depth strategy).

### Fixtures - NOT in Version Control
**IMPORTANT: Fixture files (JSON seed data) must NOT be committed to version control.**

- Fixtures are gitignored via `**/fixtures/*.json`
- Seed data is managed separately from code (via admin, shared storage, or documentation)
- If you create fixture files for local testing, they stay local
- Never use `git add -f` to force-add fixture files
- Do NOT create management commands to seed data - use Django's fixture system instead

## SharedMemoryModel

All concrete Django models must use `SharedMemoryModel` (imported from `evennia.utils.idmapper.models`, never `evennia.utils.models`). It is the repo's identity-map cache — trust it; don't reinvent caching, `resolve_*`/`batch_fetch_*` helpers, or cache-flushing around it.

**For the import-path rule, the when-to-use guidance, and the "Trust the Identity Map" N+1 procedure (the correct fix, the "Do NOT" list, and mutation/cached-property handling): see the `sharedmemory-model` skill.**
