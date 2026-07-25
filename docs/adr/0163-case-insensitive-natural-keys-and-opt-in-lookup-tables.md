# Natural-key lookups are case-insensitive; a tuple→pk index removes the repeat query; whole-table warming is opt-in per model

#2687 asks why `get_by_natural_key` — the fixture-load and FK-resolution path every
`NaturalKeyMixin` model shares — re-queries the database every time a row is
referenced, even though the row is already sitting in the identity map. A single
species referenced by a dozen `SpeciesStatBonus`/grant/gift rows during a fixture
load paid a full lookup query for every reference. The fix adds a process-level
index and, for a deliberately small set of tables, an opt-in whole-table warm.

## Decision

**Natural-key lookups are case-insensitive everywhere.** Text natural-key
components (`CharField`/`TextField`) match via `__iexact`; numeric and boolean
components keep exact matching. There is no case in which two spellings of the
same natural key should resolve to different rows — a fixture author and an admin
typing "Fire Bolt" versus "fire bolt" mean the same content.

**The index stores `tuple -> pk`, never `-> instance`.** `_NK_PK_INDEX` is a
module-level `dict[type, dict[tuple, int]]`, keyed per model via `index_owner()`
(which resolves to `__dbclass__` so a proxy and its concrete model share one
index). A hit resolves through `self.get(pk=cached_pk)`, which for a
`SharedMemoryModel` is a pure identity-map lookup — zero queries — and for the 7
`NaturalKeyMixin` models that are plain `models.Model` (no identity map) is a
primary-key `SELECT`, still cheaper than the `iexact` scan it replaces. A dead
entry (row deleted, or a pk recycled by a rolled-back test transaction) is
self-healing: `DoesNotExist` on the cached pk drops the entry and falls through to
a fresh natural-key query.

**Whole-table warming (`NaturalKeyConfig.lookup_table = True`) is opt-in per
model, not automatic.** A warmed table's `get_by_natural_key` never issues an
`iexact` query at all — it loads the whole table once via `warm_lookup_table()`
and answers every subsequent lookup from the index. This is deliberately not the
default: some natural-key tables are large and must never be bulk-loaded on a
lookup a caller expected to be cheap. Whether a table is small-and-always-used
(a catalog like `ConditionTemplate` or `Trait`) versus large-and-growable
(authored content like `ThreatPool` or `RampartElementProfile`) is a per-model
judgement the model author states explicitly, not something the framework can
infer from schema alone. `warm_lookup_table()` refuses (raises
`NaturalKeyConfigError`) if the natural key contains a `ForeignKey` component,
because building the index calls `natural_key()` per row, which traverses FK
descriptors and would cost a query per row — the opposite of the point.

**Case-variant duplicate rows are now a loud content bug, not a silent one.** On
a lazy (non-lookup-table) model, two rows whose natural keys casefold to the same
value make `get_by_natural_key` raise `MultipleObjectsReturned` — the same class
of failure the old case-sensitive `.get()` never saw, because "Fire" and "fire"
used to resolve independently. This is the case-insensitivity decision above,
carried through to its logical consequence, not a new defect; it is loud (an
exception), not silent. On a `lookup_table` model the same collision is caught
earlier and more precisely: `warm_lookup_table()` raises with both offending pks
named, at warm time.

**Known limitation: `queryset.update(name=...)` bypasses `save()`.** The index is
invalidated in `NaturalKeyMixin.save()`, which a bulk `.update()` never calls —
so a bulk rename leaves a stale index entry pointing the old key at the renamed
row. This is the same class of hazard the Evennia identity map already has
(`.update()` does not refresh cached instances either); it is not a new failure
mode this change introduces.

## Why tuple→pk, not tuple→instance

Caching the resolved instance directly was rejected: the index would then be able
to retain an instance and grow without bound as the identity map's own contents
grew, instance freshness would become the index's problem instead of staying the
identity map's, and a deleted row would need explicit index maintenance instead of
self-healing on `DoesNotExist`. Storing a pk keeps the index a pure fast-path over
`self.get(pk=...)`, which is already the identity map's job to make cheap.

## Rejected alternatives

- **Eager indexing in `cache_instance`** — populate the index the moment any
  instance enters the identity map, rather than lazily on first
  `get_by_natural_key` lookup. Rejected: `natural_key()` traverses FK descriptors
  to build its tuple, so eager indexing would fire a query per instance across
  every one of the ~180 `NaturalKeyMixin` models, including hot game-loop paths
  that never call `get_by_natural_key` at all. The lazy, on-first-lookup approach
  pays the cost only where the caller already asked for it.
- **Dual-keying `__instance_cache__` directly** — store the natural key as a
  second key into Evennia's own identity-map dict instead of a separate index.
  Rejected: `cached_all()` and `get_all_cached_instances()` both return
  `__instance_cache__.values()`, so every row would appear twice in any code that
  iterates "all cached instances" — a correctness bug, not just a memory cost.
- **`Upper()` functional unique indexes (for now)** — add a PostgreSQL functional
  index so a cold `__iexact` lookup can use a btree instead of a sequential scan.
  Rejected for now: opt-in lookup tables already remove the need for a cold
  `iexact` query on every table where warming makes sense, so a ~150-model
  migration is not justified against a cost nobody has measured. **Trigger for
  revisiting: a measured slow cold lookup on a large lazy (non-lookup-table)
  model** — not a hypothesis about scale.

## Facts for future readers

- **180** concrete classes declare `NaturalKeyMixin` (181 raw
  `class X(...NaturalKeyMixin...)` grep hits outside migrations, minus one false
  positive: `NaturalKeyManager`'s own `models.Manager["NaturalKeyMixin"]` generic
  parameter matches the same regex). **182** `NaturalKeyConfig` declarations exist
  (a few models share a `NaturalKeyConfig` inherited from a base). **173** of the
  180 are concrete, registered models with both `NaturalKeyMixin` and
  `SharedMemoryModel` in their MRO — enforced by a guard test walking
  `django.apps.apps.get_models()`.
- The other **7** declare `NaturalKeyMixin` but have no `SharedMemoryModel`
  anywhere in their MRO, so they have no identity map: 5 subclasses of
  `ConditionOrStageEffect` (plain `models.Model`), plus `PathCodexGrant` and
  `PathGiftGrant` (also plain `models.Model`, each `# noqa: SHARED_MEMORY`). For
  these, `get(pk=N)` after an index hit is a real query — the index still helps
  (a primary-key lookup replacing an `iexact` lookup, which on PostgreSQL is a
  sequential scan) but it is **not** a zero-query win. `NaturalKeyMixin.save()`
  invalidation still runs correctly for all 7 (the mixin precedes `models.Model`
  in each of their own base lists).
- **The MRO invariant is "`NaturalKeyMixin` precedes `SharedMemoryModel`"**, not
  "is the first base." Two models, `VowSituationalPerkSituation` and
  `VowSituationalPerkRung`, list `SituationRequirementMixin` first — harmless,
  because that mixin defines no `save()` of its own, but the invariant was being
  asserted rather than enforced until this branch's guard test made it real.
- **The SQLite fast tier is weak evidence for case-insensitivity behaviour.**
  SQLite's `LIKE` is already ASCII-case-insensitive and text-converts numeric
  operands, so a behavioural assertion that a wrong-cased value still matches can
  pass on SQLite even when the underlying lookup is broken — proven by mutation-
  testing `_text_lookup_key` to return `__iexact` unconditionally and watching
  `test_integer_component_matches_exactly` still pass. Prefer asserting the
  lookup-dict/index-key shape directly; treat CI's PostgreSQL parity run as the
  real gate for case-sensitivity behaviour.
- **This branch also closes #2679**, which independently proposed a per-manager-
  instance `_name_cache` for the same symptom on `ThreatPool.objects.get(name=...)`
  and `RampartElementProfile.objects.get(name=...)`
  (`world/magic/services/effect_handlers.py:295,585`). #2679's design was
  unworkable as written (a manager-instance cache is useless across
  `db_manager()`'s manager-copy behaviour on the loaddata path, and it cached
  instances rather than pks — the same problem rejected above). Both call sites
  were converted to `get_by_natural_key`, which now covers them for free; #2679
  was closed as superseded rather than implemented separately.

> Status: accepted · Source: issue #2687 (case-insensitive natural-key resolution
> + opt-in lookup tables) · relates to ADR-0008 (SharedMemoryModel); supersedes
> nothing.
