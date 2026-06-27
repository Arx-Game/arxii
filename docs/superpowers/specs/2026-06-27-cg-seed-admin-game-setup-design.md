# CG-World Seed + Admin "Game Setup" Hub — Design

**Date:** 2026-06-27
**Issues:** #1333 (seed CG-world content), child of #651 / epic #1220 (Phase A)
**Status:** Design (pending spec review)

## Motivation

A freshly-seeded dev database cannot run character creation today. The Big Button
(`seed_dev_database()` via `src/web/admin/seed_views.py`) seeds **rules** content
(checks, magic, items, combat, consent) but **not** the character-creation **world**
content the CG pipeline / `finalize_character` require: `StartingArea`, `Beginnings`
(+ allowed species), `Species`, `Gender`, `TarotCard`, `Path`, `Tradition`,
`HeightBand`, `Build`, the 12 stat `Trait`s, and the `Available`/`Active` `Roster`s.
That content exists only ad-hoc in the test mixin
`FinalizationTestMixin._setup_finalization_base`
(`src/world/character_creation/tests/test_services.py:61`).

This closes the last seam between "Big Button produces rules" and "a fresh DB can
actually run CG" — and adds the admin orientation surface that assembles the
clone→seed→tweak→export story a spinoff author follows.

## Scope

Two deliverables:

1. **`world/seeds/character_creation.py`** — a new `seed_character_creation_dev()`
   seed master promoting the test mixin's CG content into real seed rows.
2. **An admin "Game Setup" hub view** — a superuser-only `admin_view()` on
   `ArxAdminSite` that assembles the clone→seed→tweak→export flow as wayfinding +
   a live content inventory, reusing existing surfaces.

### Out of scope

- **#1221 (Phase B tuning dashboard)** — sliders, Monte Carlo, django-unfold + HTMX.
  This spec's hub is read-only wayfinding + inventory; it does not pre-empt Phase B,
  which layers on top later.
- **Game theme/configuration** (instance name, branding) — a noted future direction,
  not built here. The hub's wording stays generic ("Welcome to a new Arx-based
  instance") so it fits both the main Arx game and spinoffs.
- **New authoring affordances** — the hub routes to existing admin CRUD; it does not
  add wizards or quick-author forms.
- New models, migrations, fixtures, or data migrations. Content-only; schema exists.

## Deliverable 1 — `world/seeds/character_creation.py`

### What it creates

A `seed_character_creation_dev()` master, idempotent (`get_or_create` /
create-if-missing, never overwrites, never deletes — the #651 invariant). Promotes
`FinalizationTestMixin._setup_finalization_base`'s content into shared seed helpers:

- `Realm` → `StartingArea` (`access_level=ALL`), `Species`
- `Beginnings` (FK `starting_area`, `is_active=True`) + M2M `allowed_species` → `Species`
- `Gender`, `TarotCard` (`ArcanaType.MAJOR`), `Heritage`, `Pronouns`
- `HeightBand`, `Build` (`is_cg_selectable=True`)
- The 12 stat `Trait`s (`DEFAULT_STATS`, `TraitType.STAT`) — `get_or_create` by name
- `Path` (PROSPECT stage, `minimum_level=1`), `Tradition`
- `Available` / `Active` `Roster`s — `get_or_create` by name

Spoilers stay placeholders (existing `PLACEHOLDER_MARK` / `CONTENT_REPO_PATH` pattern);
no spoilers in VCS.

### Cluster registration & ordering

Registered in `CLUSTER_SEEDERS` (`src/world/seeds/clusters.py`) as
`"character_creation"` — added at the end of the dict literal, so the full iteration
order becomes:
`checks → magic → items → combat → consent → character_creation`.

**Why it must follow `magic` (corrected against the issue body):** `Beginnings` does **not**
FK into magic content directly — it FKs `starting_area` (→ `Realm`) and an M2M
`allowed_species` (→ `Species`). The real dependency is CG-time: `finalize_character`
expects a selectable `Cantrip` (from `seed_cantrip_starter_catalog()`, seeded by the
magic cluster) and a `Resonance` / `TechniqueStyle`. So magic must run first so those
exist when a finalized character picks them. Ordering is belt-and-suspenders anyway —
idempotency holds regardless — but the documented reason is the cantrip/resonance pick,
not a `Beginnings`→magic FK.

### Reuse (anti-reinvention)

- `FinalizationTestMixin._setup_finalization_base` is the content source — promote its
  `get_or_create` calls into the seeder; the mixin keeps calling the same helpers
  (factories-as-seed-data principle: one source of truth for tests + seed).
- The selectable cantrip is already seeded by `seed_cantrip_starter_catalog()` (magic
  cluster) — **do not mint a cantrip here**.
- No new CG-world models — reuses the existing `character_creation` / `character_sheets`
  / `traits` / `classes` / `magic` models.

## Deliverable 2 — Admin "Game Setup" hub view

### Access & wiring

A `admin_view()` on `ArxAdminSite` (mirrors how `seed_confirm` / `export_preview` are
wired: a superuser-gated function view + template, **not** a ModelAdmin). URL follows
the existing underscore convention (e.g. `admin:_setup`, alongside `_seed` /
`_export_preview`). Registered in `src/web/admin/urls.py`.

Reachable two ways:
- A prominent link on the admin index header (alongside the existing Export/Import
  links).
- As the landing after a successful `seed_run` (so "I clicked the Big Button" drops
  the author where they'd want to be next).

### Template — three regions

1. **The flow narrative** — static, generic welcome ("Welcome to a new Arx-based
   instance") + the four steps in order: *Seed defaults → Author content → Tune
   mechanics → Export your game*. Each step links to its surface. Pure wayfinding
   text; no logic.

2. **Content inventory (live)** — a read-only row-count table. Introduce a **new**
   helper (e.g. `seeded_models_by_cluster()` in `clusters.py`) returning
   `{cluster_name: [models]}`; **do not change `seeded_models()`'s flat-list shape**
   (`database.py:_row_count()` depends on it). The inventory reads e.g.
   "character_creation: 4 StartingAreas, 12 Traits, …" per cluster. Empty cell = a
   content gap the author should fill. Computed at request time from
   `Model.objects.count()`; no caching (the seeded set is small; the view is
   superuser-only/infrequent; live correctness beats speed — counts must reflect a
   just-run seed or a just-made edit).

3. **Action shortcuts** — links to: the Big Button (`_seed`), the existing domain
   admin CRUD changelists (the `APP_GROUPS` "World" group already lists
   `character_creation`, `species`, `classes`, `traits`, `magic`, `combat`… — link
   straight to each app's changelist), and Export/Import (`_export_preview` /
   `_import_upload`). No new authoring affordances.

### Permissions

`admin_view()` enforces staff/superuser via the existing admin RBAC — same gate as
the Big Button. Consistent with ADR-0022 (admin-hosted, reuse admin RBAC). No React,
no generated API types, no CSRF boilerplate (this is read-only + the existing seed
POST is already CSRF-wired).

## Data flow & error handling

- **Seed orchestrator** iterates `CLUSTER_SEEDERS` in order; the CG cluster fills the
  CG-world content gap. `SeedReport` already reports created-delta per cluster; the CG
  cluster participates in that count automatically.
- **Hub** performs no writes; it only reads counts + renders links. Its only failure
  mode is a DB read error — surfaced as a standard Django admin error; no special
  handling.
- **Seed failures** propagate as a normal admin `messages.error`, matching the
  existing `seed_run` pattern.

## Testing

Focused integration tests (per the repo's E2E-over-fine-grained-unit preference):

1. **Seed idempotency + non-overwrite** (the #651 "done when" gates): a second
   `seed_dev_database()` run is a pure no-op; a hand-edited seeded CG row survives
   re-seed. Extend the existing seed test suite with the CG cluster.
2. **Fresh-DB CG runs:** after seeding a clean DB, `finalize_character` succeeds
   against the seeded CG-world content (the real-CG-pipeline smoke the #1333 body
   calls out) — the proof the content gap is closed.
3. **Hub view:** superuser GET renders all three regions with correct row counts;
   non-superuser is denied (403) — mirrors the existing `seed_views` permission test
   pattern.

## Docs (in-PR, per "docs are directives")

- `docs/roadmap/seed-and-integration-tests.md` — mark the Phase 3 CG-content item done;
  note the seeder + the Game Setup hub.
- `docs/systems/INDEX.md` + `docs/systems/character_creation.md` — record the seeded
  CG-world content + the admin Game Setup hub.
- `src/web/admin/CLAUDE.md` — add the Game Setup hub to the admin doc (alongside
  Export/Import).
- `docs/roadmap/ROADMAP.md` — note the CG orientation surface; move the CG domain
  status forward (skeleton → partial) only as far as is truthful.
- Regenerate `docs/systems/MODEL_MAP.md` only if a model/FK changed (none does here;
  no regen expected).

## Dependencies

None new. No django-unfold yet (that's #1221). No new models, no migration.

## Open follow-ups (not this PR)

- Phase B (#1221) tuning dashboard layers onto this hub.
- Game theme / instance configuration (name, branding) — future direction noted in the
  hub wording; not built.
- **Seed-source unification pass (deferred, non-blocking):** some CG-world content may
  already be created independently elsewhere (e.g. by a magic-cluster helper or a
  progression seeder). Per-cluster, on first contact: grep for other `get_or_create` /
  seed sites creating the same rows and consolidate to one source (factories-as-seed-data
  principle). Not a precondition for this PR — unify as each item is authored, not as a
  separate up-front audit.
