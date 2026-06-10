# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo. **Invariants live
here; procedures and reference live in skills and docs — load them when the task
calls for it.** Full command reference: `docs/dev-commands.md`.

## Agent Communication

**Questions in user-facing text must be unambiguous.** Any sentence you show the
user that ends in `?` must either be issued through `AskUserQuestion` (the answer
is required to proceed) or be restated as a statement when it's rhetorical
self-direction (e.g. "Checking whether the skill expects a reviewer dispatch
step." — not "Does the skill expect a reviewer dispatch step?"). When in doubt, no
`?` in user-facing text outside `AskUserQuestion`.

<!-- TEMP HARNESS-BUNDLING-WORKAROUND — removal tracked in GH #883 (#647 closed without a successor) -->
**[TEMP] Load the `grounding-before-action` skill at session start.** It works
around a Claude Code 2.1.158 regression (a tool result co-emitted with the call it
depends on is invisible at compose time → confabulation; caused real erroneous
GitHub edits). The skill carries the full rule set; the essentials: emit
`AskUserQuestion` solo, echo the chosen answer back before any irreversible action,
and verify issue number↔title before any mutation. Temporary — removal tracked in
**#883** (grep `HARNESS-BUNDLING-WORKAROUND`); delete when the harness is fixed.

## Git Workflow

- **Never work directly on main.** Branch first: `git checkout -b feature-name`.
  After a squash-merge: `git checkout main && git pull && git branch -D feature-name`.
- **No `cd &&` compound commands.** Use `git -C /path <command>` for git, or
  absolute paths / a tool's own directory flag otherwise. (Claude Code on Windows
  flags every `cd && <command>` for manual approval as a bare-repo-attack
  mitigation, which blocks automation — a workaround for a CC permission behavior,
  mid-2026. Relax if future releases stop flagging it.)
- **`gh` discipline** (see the `github-operations` skill): take new issue/PR
  numbers from the URL the create command returns — never compute `N+1` (issues and
  PRs share one counter); verify number↔title before any mutation; keep issue/PR
  writes one-per-message. Read-only `gh api` calls are fine. Branch protection on
  `main` plus the maintainer PAT scope are the safety rails.
- **End-to-end issue → merged-PR work:** use the `issue-to-merged-pr` skill (branch
  creation, PR opening, CI watching, post-merge cleanup). Outside it, plain
  `gh pr create` is fine.

### Spec review happens on the issue, gated by labels

New feature specs live in the **GitHub issue body** (between `<!-- spec:start -->`
and `<!-- spec:end -->`), not as committed files. (Pre-convention specs still live
in `docs/superpowers/`; being triaged — see #660.) The `issue-to-merged-pr` flow
drafts the spec, flags the team, then **stops** until a human org member approves.
**Labels are the source of truth:**

- `status:spec-draft` — writing the spec into the issue body
- `status:spec-review` — spec posted; awaiting approval (agent has exited)
- `spec:approved` — **member-only gate.** On our public repo only Triage+ org
  members can apply labels, so this label *is* the authorization boundary.
  **Agents MUST NEVER apply `spec:approved`** — hold the PAT but self-restrain and
  only poll for it.
- `status:implementing` — approved; building toward a PR (normal code review)

Comments never gate (anyone can comment on a public issue). Labels + assignment +
close state also drive the **Project board** automatically (see
`docs/project-board-automation.md`) — change the label/assignment; don't hand-move
cards. The `superpowers:writing-plans` output is ephemeral (worktree-only, never
committed).

## Architecture Overview

Arx II is a **web-first multiplayer RPG** on the Evennia framework. The React
frontend is the primary game interface — design every feature for modern web UX
(interactive components, visual feedback, responsive layouts). Telnet/MUD access is
a secondary compatibility goal, **not** the design target: do not design features
around text-command-and-response patterns.

The backend is **action-centric**: both the web frontend (WebSocket / REST
dispatch) and telnet commands converge on `action.run()`. An `Action`
(`src/actions/`) owns its prerequisites (permission checks) and execution, calling
**service functions** (`src/flows/service_functions/`) for state changes. Game logic
lives in actions and the service functions they call; commands are a thin
telnet-compatibility layer with no business logic. **Flows** (`src/flows/`) are a
separate reactive layer — triggers run flows in response to emitted events (e.g.
condition decay, reactive effects).

For each layer's detail, read the code-adjacent app guides (also loaded when you
work in those dirs): **`src/actions/CLAUDE.md`** (action lifecycle, enhancements,
effects), **`src/commands/CLAUDE.md`** (telnet layer), **`src/flows/CLAUDE.md`**
(flows, triggers, object states). Custom typeclasses live in `src/typeclasses/`;
server config in `src/server/`. Python 3.13+ (mise), Node 20, `uv` for deps; env
file `src/.env`; Django commands run from `src/`.

## Where to Look (consult before starting)

- **Roadmap** — `docs/roadmap/ROADMAP.md` before starting a new system/feature
  (status, design principles, per-domain constraints, MVP gaps; domain stubs like
  `docs/roadmap/combat.md` go deeper).
- **Systems index** — `docs/systems/INDEX.md` before features touching multiple
  systems (existing models, key functions, integration points, reusable patterns;
  per-system docs like `docs/systems/magic.md` go deeper). Prevents reinventing
  existing functionality.
- **Model map** — `docs/systems/MODEL_MAP.md` for cross-app FK relationships and
  service-function signatures. Auto-generated; regenerate after major model changes
  via `uv run python tools/introspect_models.py`.
- **Django development** (models, views, APIs, tests) — `django_notes.md`.
- **Evennia migration quirks** — `docs/evennia-quirks.md`. Use `arx manage
  makemigrations` (custom command that prevents phantom Evennia-library migrations).

## Anti-Reinvention — REQUIRED for feature design

**Every feature-design workflow MUST include an explicit "no reinventing the wheel"
pass before the spec is finalized.** Sprawl from parallel
components/dataclasses/enums/helpers is the most expensive failure mode in this
codebase. The core rule: **existing code is the source of truth; docs (INDEX,
MODEL_MAP, architecture/roadmap, prior agent summaries) are stale hints.** Before
approving any proposed new surface, verify it against code, find a live caller, and
prefer reuse-with-extension over build-new — then present consolidations for
ratification. The `verify-against-code` skill carries the labeling procedure
(`[BUILT & WIRED]` / `[BUILT, NOT WIRED]` / `[ABSENT]`), the ledger format, and the
recurring-traps list. **Use it.**

## Database & Code Quality Invariants

Database design:

- **No JSON fields.** Each setting/configuration is a proper column with validation
  and indexing. Use foreign keys, real data types, DB constraints — all data
  queryable with standard Django ORM.
- **Avoid direct FKs to ObjectDB.** Evennia's ObjectDB is a generic base for all
  game objects; an FK to it is almost always too broad. Use a specific model
  (Persona, RosterEntry, CharacterSheet, RoomProfile). Ask: "could this be a vase of
  flowers?" Only use ObjectDB when the FK genuinely needs any object type. Same rule
  applies to service-function parameter annotations — enforced by
  `tools/lint_objectdb_param.py` (`objectdb-param` hook); use `# noqa: OBJECTDB_PARAM`
  when ObjectDB is genuinely right. Lint scope expands one app at a time (the
  `files:` regex in `.pre-commit-config.yaml`); new code in in-scope modules must
  pass clean.

Code quality (always-on; full list in `django_notes.md`):

- **No relative imports** — absolute only (`from world.roster.models import Roster`).
- **No Django signals** — explicit, testable service-function calls instead.
- **No data migrations pre-production** — schema migrations only; no `RunPython`
  backfills (no meaningful rows yet).
- **Preserve the dev database** — never drop/flush/destroy it except in dire need.
- **PostgreSQL only (production)** — use PG features directly (CTEs, materialized
  views, `DISTINCT ON`, JSONB); no DB-agnostic workarounds.
- **100-char line limit.** Use `.env` for configurable settings.

The full standards (type annotations + `ty`, model-instance preference, avoid dict
returns, `types.py`, `Meta.ordering`, inheritance-over-protocols, denormalization,
`TextChoices` in `constants.py`, no-queries-in-loops, no-management-commands,
no-backwards-compat, `# noqa` policy + custom-linter tokens) live in `django_notes.md`.

### Django & API specifics

- Use `TextChoices`/`IntegerChoices` for model field choices.
- All ViewSets must have filters, pagination, and permission classes. One ViewSet
  per related-model CRUD; no implicit first-item selection; validation in
  serializers, permissions in permission classes; never `str(exc)` in responses.
  Full rules: "ViewSet & API Design (Standards)" in `django_notes.md`.
- Use FactoryBoy for all test data with `setUpTestData`; focus tests on application
  logic, not Django built-ins. The `django_get_or_create` gotcha (silently drops
  non-lookup kwargs when the row pre-exists) + the `_create` fix: see `django_notes.md`.
- **New apps: avoid multiple migrations during development** — see
  `docs/evennia-quirks.md`.
- **SharedMemoryModel** — all concrete models use it (import from
  `evennia.utils.idmapper.models`, **never** `evennia.utils.models`). It's the
  identity-map cache: trust it; don't reinvent `resolve_*`/`batch_fetch_*` helpers
  or cache-flushing. See the `sharedmemory-model` skill.
- **Fixtures are NOT in version control** (gitignored via `**/fixtures/*.json`).
  Never `git add -f` a fixture; don't write management commands to seed data — use
  Django's fixture system. Seed data is managed separately (admin, shared storage, docs).

## Testing

**Always use `arx test` or its `just` wrappers** — never `uv run python -m`,
`python manage.py test`, or sourcing venvs. Two tiers: SQLite for fast local
iteration (`just test-fast <app>`), Postgres for parity (`just test-parity` /
`just regression`), which CI runs on every PR.

Run the fast SQLite tier for the apps you changed, then push and **monitor the PR**,
fixing what CI catches. **CI is the full-regression gate** — run a local
`just regression` only to reproduce a CI failure the fast tier doesn't surface. For
the per-app tier table, recipes, `@tag("postgres")` decisions, the `--keepdb`
pitfall, invocation gotchas (`world.`-prefixed test paths, no `-v`, `uv run` for
ruff/pre-commit), and the "never rely on Evennia defaults in service functions"
rule: see the `running-tests` skill.

## Proactive Quality Checks

- **After editing Python:** run `arx test <app>` for the affected app (don't wait to
  be asked) and `ruff check <file>` on changed files.
- **After editing TypeScript:** run `pnpm typecheck` and `pnpm lint` on changed files.
- **Dead-code removal (careful — active development):** check for TODO/FIXME first;
  stubs/empty implementations/unused imports may be intentional placeholders. When
  in doubt, ASK before removing — only remove clearly obsolete code.

## Completing a Unit of Work

- **Update the roadmap** — mark completed phases/items in the relevant
  `docs/roadmap/*.md`; document what was built, not just that it's done.
- **Run the fast SQLite tier** for the apps you touched (`just test-fast <app>`).
- **Push and let CI gate regression** — CI runs the Postgres parity suite on every
  PR; monitor the PR and fix failures there.
