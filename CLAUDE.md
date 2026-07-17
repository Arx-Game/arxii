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

## Tool & Subagent Sequencing

**Repo-mutating operations (`git`, `rm`, `Edit`, `Write`, and implementer
subagents) run strictly sequentially — one per message, verify the result
before the next.** Parallelism is only for read-only fan-out (greps, reads,
Explore/research agents). Two concrete failure modes motivate this:

- **Parallel implementer subagents on a shared worktree corrupt the git
  index** — they revert each other's uncommitted edits and cross-contaminate
  commits. Dispatch one, await it, verify the commit actually landed
  (`git log -1`), then the next.
- **Batched mutating tool calls cascade-cancel**: when one call in a parallel
  batch errors or hits an approval prompt, the harness cancels every sibling
  in that batch, and most of the intended work silently doesn't run.
- **Subagents must run every command in the foreground.** Background completion
  notifications re-invoke the main loop only — a subagent that backgrounds a
  command and ends its turn "waiting for the notification" dies silently holding
  uncommitted work (two stalls during #1909). Put a foreground-only instruction
  in every implementer/fix dispatch prompt. The instruction alone does not fully
  prevent it (6+ recurrences on 2026-07-06/07) — when a subagent stalls this
  way, the recovery is cheap and reliable: **resume it with a message** ordering
  it to re-run the checks in the foreground and commit before ending its turn.
- **Subagent dispatch prompts must anchor the worktree.** A subagent's FIRST
  action must be `cd <worktree>` then `pwd` + `git status --short`, verifying
  branch and tree before any edit; every path it edits and every test it runs
  must live inside the worktree. An absolute worktree path in the prompt is not
  enough — a subagent that skips the anchor step drifts into the shared main
  checkout, where concurrent sessions clobber its uncommitted work (near-miss
  on #2029).

Destructive or approval-gated git operations (`reset --hard`, force-push) go
alone in their own message. Never cite an issue/PR number that wasn't read
back from the creating command's own stdout.

## Git Workflow

- **Never work directly on main.** Branch first: `git checkout -b feature-name`.
  After a squash-merge: `git checkout main && git pull && git branch -D feature-name`.
- **Finishing a branch always means push + open a PR — never a local merge.** When a
  skill (e.g. `superpowers:finishing-a-development-branch`) offers a menu of
  merge/PR/keep/discard, skip straight to push + PR without asking; only ask if the
  user wants to keep-as-is or discard instead. This follows from the merge-queue rule
  below (a local merge bypasses CI and the queue entirely) — don't re-ask it as an
  open question each time.
- **`main` uses a merge queue (#991; see ADR-0021).** Once a PR is green, **enqueue it**
  (`gh pr merge --auto --squash`, or `enqueue-pr.sh` in the `issue-to-merged-pr`
  skill) and stop — do not re-sync with main or merge by hand. The queue
  re-tests the PR on top of the latest main and merges in order; a human
  approval is the only remaining gate. A migration collision shows up as the
  loser being bounced from the queue (others keep flowing) — fix it with
  `arx manage makemigrations --merge` (or renumber), push, re-enqueue.
- **No `cd &&` compound commands.** Use `git -C /path <command>` for git, or
  absolute paths / a tool's own directory flag otherwise. (Claude Code on Windows
  flags every `cd && <command>` for manual approval as a bare-repo-attack
  mitigation, which blocks automation — a workaround for a CC permission behavior,
  mid-2026. Relax if future releases stop flagging it.)
- **Worktrees are mandatory** — always work in a git worktree under
  `.claude/worktrees/` (the `arxii-worktrees` named volume in the devcontainer),
  never in the main checkout. Other paths land on the slow 9p bind mount, where
  a worktree's `uv sync` takes ~10 min instead of <1 s via hardlinks from the
  colocated `UV_CACHE_DIR`. The `using-git-worktrees` skill makes this mandatory
  (no opt-out) and creates the worktree automatically; see
  `docs/devcontainer-setup.md`.
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
and `<!-- spec:end -->`), not as committed files (see ADR-0020). (Pre-convention specs still live
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
  via `uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md` (the
  script prints to stdout — the redirect is required, not optional).
- **Django development** (models, views, APIs, tests) — `django_notes.md`.
- **Evennia migration quirks** — `docs/evennia-quirks.md`. Use `arx manage
  makemigrations` (custom command that prevents phantom Evennia-library migrations).
- **Decision log** — `docs/adr/README.md` before changing architecture, a
  pipeline/contract, models, or a design tenet; an ADR records *why* a decision was
  made and the alternative that was rejected. Don't re-litigate a recorded decision.
- **Glossary** — `AGENT_GLOSSARY_MAP.md` (+ the app's `AGENT_GLOSSARY.md` next to its
  code) before designing or naming anything; use the canonical terms, not the
  `_Avoid_` synonyms.

### Decisions & Vocabulary

ADRs (`docs/adr/`) hold the *why* behind hard, surprising, traded-off decisions and
the rejected alternatives; the glossary (`AGENT_GLOSSARY_MAP.md` → per-app
`AGENT_GLOSSARY.md`) holds the canonical ubiquitous language. The
`domain-glossary-and-adr` skill keeps both current; `design-vocabulary` and
`architecture-cleanup` enable periodic deepening. (Note: "module" stays a code
unit — it is NOT redefined to mean "component".)

## Docs Are Directives — Keep Them in Tandem

In the agentic era, docs are **directives that you and other agents act on**, not
commentary. A stale doc actively misleads — it is worse than no doc, because it is
trusted. So **a change is not complete until the docs that describe it change in the
same PR.** When you change behavior, architecture, a pipeline/flow, models, APIs, or
service-function signatures, update the docs that describe them as part of the work:

- **System doc + index** — update `docs/systems/<system>.md` and
  `docs/systems/INDEX.md` when you add/rename/remove models, services, enums,
  exceptions, or endpoints.
- **Model map** — regenerate `docs/systems/MODEL_MAP.md`
  (`uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md`) after
  model/FK or service-signature changes.
- **Architecture doc** — update the relevant `docs/architecture/*.md` (including its
  diagrams) when you change a pipeline, contract, or flow it documents.
- **Roadmap** — mark the relevant `docs/roadmap/*.md` and record *what was built*.
- **Decision log** — when you make a hard-to-reverse, surprising, real-trade-off
  decision, record it as a one-paragraph ADR in `docs/adr/` in the same PR; when you
  reverse one, mark the old ADR superseded.
- **Glossary** — when you add, rename, or remove a domain term, update the app's
  `AGENT_GLOSSARY.md` (+ the root `AGENT_GLOSSARY_MAP.md`) in the same PR.
- **Fix-on-sight** — if you touch code a doc describes and find the doc already wrong,
  correct it at the source in the same PR (use the `verify-against-code` skill's
  `[BUILT & WIRED]` / `[BUILT, NOT WIRED]` / `[ABSENT]` labeling).

This does not contradict "code is the source of truth" (see Anti-Reinvention): code
is what's *true*; this invariant keeps the docs *trustworthy enough to be directives*.
A change may legitimately need no doc update — but decide that deliberately, per the
list above; don't default to skipping.

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

## Fold In, Don't File

Trivial review-surfaced gaps (a missing test, a dedup, a wiring nit) get fixed in
the current branch/PR now or dropped — never filed as a follow-up issue, no
exceptions. File only for something substantial enough to need its own PR
(separable system, scope beyond the current issue, a design question needing a
human call), with the reason stated in the issue body. Overrides any skill step
that says to file a follow-up — see `issue-to-merged-pr`'s SKILL.md for detail.

## Database & Code Quality Invariants

Database design:

- **No JSON fields** (see ADR-0007). Each setting/configuration is a proper column
  with validation and indexing. Use foreign keys, real data types, DB constraints —
  all data queryable with standard Django ORM.
- **Avoid direct FKs to ObjectDB.** Evennia's ObjectDB is a generic base for all
  game objects; an FK to it is almost always too broad. Use a specific model
  (Persona, RosterEntry, CharacterSheet, RoomProfile). Ask: "could this be a vase of
  flowers?" Only use ObjectDB when the FK genuinely needs any object type. Same rule
  applies to service-function parameter annotations — enforced by
  `tools/lint_objectdb_param.py` (`objectdb-param` hook); use `# noqa: OBJECTDB_PARAM`
  when ObjectDB is genuinely right. Lint scope expands one app at a time (the
  `files:` regex in `.pre-commit-config.yaml`); new code in in-scope modules must
  pass clean.
- **FK direction — depend specific→general** (see ADR-0010). When a link joins two systems, decide
  which side the FK belongs on *deliberately*: it lives on the more specific/dependent
  system and points at the reusable primitive, **never** on the primitive. Don't anchor
  it on whichever app you happen to be editing — a general model (e.g. `Secret`) must not
  end up importing every system that references it. (e.g. `CharacterDistinction.secret →
  Secret`, so `secrets` stays dependency-free while consumers point into it.)

Code quality (always-on; full list in `django_notes.md`):

- **No relative imports** — absolute only (`from world.roster.models import Roster`).
- **Never edit dependency code.** `site-packages` (Evennia included) is read-only; every
  linter, quality sweep, or fix pass must exclude Django apps we don't own — flag an
  upstream problem, never "fix" it in the vendored copy. Worktree venvs hardlink from
  the shared uv cache, so a venv edit silently poisons the cache and resurfaces later
  as impossible same-locked-rev-different-bytes failures (admin.E038 incident,
  2026-07-17: an admin sweep added `autocomplete_fields` to Evennia's own admin).
- **No Django signals** — explicit, testable service-function calls instead (see ADR-0009).
- **No data migrations pre-production** — schema migrations only; no `RunPython`
  backfills (no meaningful rows yet) (see ADR-0013).
- **Preserve the dev database** — never drop/flush/destroy it except in dire need.
- **PostgreSQL only (production)** — use PG features directly (CTEs, materialized
  views, `DISTINCT ON`, JSONB); no DB-agnostic workarounds (see ADR-0012).
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
- **SharedMemoryModel** (see ADR-0008) — all concrete models use it (import from
  `evennia.utils.idmapper.models`, **never** `evennia.utils.models`). It's the
  identity-map cache: trust it; don't reinvent `resolve_*`/`batch_fetch_*` helpers
  or cache-flushing. See the `sharedmemory-model` skill.
- **Fixtures are NOT in version control** (gitignored via `**/fixtures/*.json`).
  Never `git add -f` a fixture; don't write management commands to seed data — use
  Django's fixture system. Seed data is managed separately (admin, shared storage, docs).
  **`loaddata` inserts; it does NOT update idmapper rows** — for re-seeding edited
  data use an upsert path (`load_entries` / `update_or_create`); see
  `docs/evennia-quirks.md` (#946).

## Testing

**Always use `arx test` or its `just` wrappers** — never `uv run python -m`,
`python manage.py test`, or sourcing venvs. Two tiers: SQLite for fast local
iteration (`just test-fast <app>`), Postgres for parity (`just test-parity` /
`just regression`), which CI runs on every PR.

**For PR work, prefer `just test-affected`** — it diffs against `origin/main`
and runs only the apps your branch touches plus import dependents, so you don't
waste time on unrelated suites. For a single app, use `just test-fast <app>`.
(Use `test-affected` for *mid-work* iteration on a multi-app change — but at the
**final pre-push moment** keep to the focused per-app `just test-fast <app>` and
skip whole-repo passes; running everything at once can crash the devcontainer.
See "Completing a Unit of Work.")

Run the fast SQLite tier for the apps you changed, then push and **monitor the PR**,
fixing what CI catches. **CI is the full-regression gate** — run a local
`just regression` only to reproduce a CI failure the fast tier doesn't surface.
**Never pipe exit-code-bearing commands (`arx test`, `git commit`) through
`tail`/`head`** — the pipe masks the exit code and buries the OK/FAILED summary
(false-green runs on #947/#948; a silently aborted commit reopened #927). Run
them bare (backgrounded if long) and read the full output. For
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

- **Update the docs in tandem** — per "Docs Are Directives," sync the
  system/architecture/INDEX/MODEL_MAP docs (and their diagrams) your change affects
  *in this PR*. A code change that leaves its docs stale is incomplete.
- **Update the roadmap** — mark completed phases/items in the relevant
  `docs/roadmap/*.md`; document what was built, not just that it's done.
- **Run the fast SQLite tier** for the apps you touched (`just test-fast <app>`).
  At this final pre-push moment keep it to the focused per-app run — **do NOT run
  `pre-commit run --all-files`, a broad `just test-affected`, or `just regression`
  as a precheck; the whole-repo pass can crash this devcontainer** (per-file hooks
  already ran at commit, and CI is the gate). If you must re-run hooks locally,
  scope to the diff: `uv run pre-commit run --from-ref origin/main --to-ref HEAD`.
- **Push and let CI gate regression** — CI runs the Postgres parity suite on every
  PR; monitor the PR and fix failures there.
