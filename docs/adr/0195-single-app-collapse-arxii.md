# ADR-0195: All first-party apps collapse into one Django app, `arxii`

**Status:** Accepted · **Date:** 2026-08-04 · **Issue:** #2906

Every first-party app collapses into **one** Django app: the `world` package **is** the
app, registered under the label `arxii`. The 66 previously-separate `world.*` apps stop
being installed apps in their own right (their sub-package directories do not move); the
27 models that lived in `actions`, `flows`, `behaviors`, `evennia_extensions`, and
`web.admin` fold in too, each via an explicit `Meta.app_label = "arxii"`. The 1,215
migration nodes those apps carried collapse into `src/world/migrations/`: 100
cost-weighted chunks (`0001_initial.py` through `0100_initial_part_100.py`, together
carrying the 1,026 `CreateModel` operations and their FKs) plus 2 renumbered tail
migrations that were already in flight when the squash landed, 102 files total, with no
migration history predating them. The 100-way split is **speed-neutral** (+1.6% versus one
giant file, within this box's run-to-run noise) - it exists for transaction-timeout
safety, smaller per-chunk lock footprint, and resumability, not performance. Per-chunk
apply time: min 0.10s, median 5.90s, max 25.95s.

**Why.** This ADR originally repeated issue #2906's opening hypothesis: that the cost was
the cross-app dependency graph, and that one app would mean no repeated project-state
rebuild. **That hypothesis was measured and falsified.** Collapsing to one app *by
itself*, using Django's own `makemigrations`-generated migration, made a fresh `migrate`
slower than `main`, not faster (roughly 2500-2940s against `main`'s 2100.2s on the same
box, same session). The real mechanism, found by reading Django's migration executor
rather than guessing at it:

- `autodetector.py` strips **every** relational field out of a new model's `CreateModel`
  unconditionally, with no cycle detection at all, and emits a separate `AddField` for
  each one. Our collapsed schema has 1,026 models and roughly 2,414 intra-app FK edges;
  Django's autodetector deferred **2,321** of them into standalone `AddField` operations.
- `state.py`'s `add_field` takes the expensive `get_related_models_recursive` path (a full
  transitive-closure re-render of the project state) for every relational `AddField`.
  `add_model` pays the same closure cost for every `CreateModel`, not only for deferred
  fields. `Migration.apply` additionally deep-copies the entire rendered state once per
  operation (`ProjectState.clone`).
- The cost is therefore **O(operations x models-in-state)**, driven by the *count of
  migration operations*, not by the number of Django apps. An app-count reduction does
  nothing about that on its own, which is exactly why the plain collapse measured slower:
  same operation count, same per-operation closure cost, plus the collapse's own added
  bookkeeping.
- A dependency-graph analysis of the collapsed schema found only **5 genuine reference
  cycles** (32 models, largest cycle 21), requiring only **49** FK edges to be deferred to
  break them. Django's autodetector had deferred 2,321 - about 47x more than the schema
  actually needs. `tools/optimize_initial_migration.py` reduces the 2,321 down to the true
  floor (146 `AddField`s: 34 cycle-breaking FKs + 112 M2M throughs) by inlining every FK
  that isn't on a cycle straight into its model's `CreateModel`, in topological order. That
  inlining, not the app collapse, is what produces the actual measured win: 1619.5s versus
  `main`'s 2100.2s, about **1.30x faster**, same session, same box (which itself varies
  roughly 20-30% run to run, so only same-session comparisons are meaningful).
- The collapse is still worth keeping, but for a narrower and different reason than
  originally claimed: Django can only express a migration dependency at `(app,
  migration)` granularity, never at the level of an individual model or field. Before the
  collapse, 46 of the 68 apps sat inside a single dependency cycle, which forced a floor of
  **1,153** unavoidably-deferred FKs no matter how the migrations inside each app were
  written. Collapsed to one app, that floor drops to the schema's true **49**. The
  `max_migration.txt` single-leaf guard from ADR-0021 also collapses from 66 independent
  sentinels to one - see "Consequences" below for why that is a real trade-off, not a pure
  win as originally stated here.

**Rejected: periodic squash/regeneration.** Squashing each app's migration history
back down to one file per app (rerun every few months) was rejected as **transitory, not
structural**: it resets operation *count* without removing the underlying 46-app
dependency cycle that forces the 1,153-edge deferral floor. The moment a new cross-app FK
lands - and cross-app FKs are exactly what a 66-app domain split encourages, since a new
feature routinely needs to relate to three or four existing domains - the cycle re-tangles
and the floor climbs back up until the next squash.

**Rejected: inlining without the collapse.** `tools/optimize_initial_migration.py`'s
topological-inlining technique is generic - it operates on any migration graph, and would
cut `main`'s 2,321 deferred `AddField`s down toward its true floor without touching the
app boundaries at all. It was rejected as the *whole* fix because that floor is not the
same number pre- and post-collapse: with 68 separate apps and 46 of them in one
dependency cycle, the floor stays at 1,153 no matter how well any single app's migrations
are inlined, because the deferral is forced at the inter-app boundary, which per-app
inlining cannot see across. Only removing the app boundary (the collapse) gets the floor
down to the schema's true 49. Inlining `main` in place remains a smaller, valid
optimization on its own; it was not pursued here because the collapse was already in
flight for the app-label reasons below, and doing both at once reaches the lower floor in
one migration rewrite instead of two.

**Consequences.**

- **One `max_migration.txt` sentinel raises merge-collision odds; it does not lower
  them.** This ADR originally claimed the opposite - that collapsing 66 independent
  sentinels to one was "strictly easier to reason about, not harder." That was wrong, and
  `CLAUDE.md`'s Git Workflow section states the corrected version: with one sentinel
  repo-wide, any two branches that both add a model or field now land in the *same* file,
  so a merge-queue collision is more likely, not less. The fix when it happens is
  unchanged (`arx manage makemigrations --merge` or renumber, push, re-enqueue) - the
  collapse traded a rare cross-app coordination problem for a more common single-file one,
  and that trade was made deliberately for the deferral-floor reason above, not because
  the sentinel itself got simpler.
- **Fresh-database bootstrap should still prefer `build_schema.py`, not `migrate`.**
  `tools/build_schema.py` builds an identical schema directly from model definitions (plus
  partition/materialized-view SQL and seeds) with no migration replay at all, in 321s -
  about 6.5x faster than `main`'s migration replay and about 5x faster than the
  collapsed-and-inlined migration replay. Schema equivalence between the two paths was
  checked at the time by a `pg_catalog` diff and reported empty. **That check was not
  sound** - #2982 later found the collapsed chain had lost the `arxii_interaction`
  partition rewrite and its composite FKs entirely, so the two paths were *not*
  equivalent when this ADR was written. The gap is closed by
  `src/world/migrations/0108_partition_interaction.py`, and equivalence is now
  machine-checked nightly by `tools/compare_schemas.py` rather than asserted once by
  hand. This ADR's migration-speed work matters for deploys that must replay migration
  *history* (e.g. an existing database moving forward one release at a time); it does
  not change which path a fresh clone or CI scratch database should take.
- **Dev databases cannot be migrated across this change.** All 1026 tables changed name
  (every `<oldapp>_<model>` table becomes `arxii_<model>`), so there is no migration path
  from a pre-collapse schema to the post-collapse one - only rebuild-and-reseed. This is a
  deliberate, ratified exception to CLAUDE.md's "preserve the dev database" rule, made
  possible only because ADR-0013 (no data migrations pre-production) already established
  that no dev database holds meaningful rows worth a migration path: deleting the
  migration history was free specifically because there was nothing to lose crossing it.
- **`app_label` no longer carries authoring-domain meaning.** Before this change, an
  app label doubled as the model's authoring domain: it grouped the Django admin index,
  named the lore repo's `fixtures/<domain>/` directory, and keyed the admin pin/exclude
  rows. With one label (`arxii`) shared by nearly every model, that signal moved to
  `core.app_domains.domain_of()`, which derives the same domain string from the model's
  *module path* instead (`world.magic.models` -> `"magic"`; `web.admin.models` ->
  `"web_admin"`) and now backs all three of those surfaces.
- **Model names must stay globally unique.** Fixtures, the admin pin/exclude toggles, and
  content export all resolve a stored `"<label>.<model>"` reference to a live model class
  via `core.app_domains.resolve_model_by_name`, which - because the label half of that
  reference is frequently stale post-collapse - resolves primarily by **name**. A name
  collision across domains is therefore a real ambiguity, not a cosmetic one:
  `resolve_model_by_name` raises `LookupError` naming every candidate rather than
  guessing, so a second model sharing a name breaks fixture loading loudly instead of
  loading the wrong row.

Narrows ADR-0013 (schema-only migrations pre-production is *why* deleting the pre-collapse
migration history cost nothing) and relates to ADR-0021 (the merge queue's single-leaf
migration guard, now guarding one sentinel instead of 66).
