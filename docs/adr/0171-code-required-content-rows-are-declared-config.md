# CONTENT_MODELS stays the model-level line; code-required rows get a declared per-row config carve-out, and per-player rows export by owner column, never name pattern

**Amends ADR-0168** — it does not supersede it. ADR-0168 settled that `CONTENT_MODELS`
registration is the seed/content boundary at the **model** level: if a model is
registered, the content repo owns every row in it and no seeder may create one. That
rule left two gaps this issue closes, both inside models that stay registered.

**Gap 1 — code-required rows had no declared dependency.** Several service functions
name a row by string literal and break without it — `world.fatigue.services` rolls a
CheckType named `"fatigue_willpower"`, `world.magic.seeds_cast` FKs an ActionTemplate
named `"Technique Cast"` that lore `Technique` fixtures also FK by natural key. Nothing
marked these as load-bearing, so a staff member tidying `checktype.json` (or a fresh
clone with no content repo yet) could delete or omit one and silently revert its
tuning, or — worse, on a first run — leave `load_world_content`'s deferred-retry loop
unable to resolve a fixture FK it can never conjure (the loop only retries against rows
the content/grid load itself creates).

**Gap 2 — some registered models mix authored and per-player rows.** `checks.checktype`
holds staff-authored checks (Melee Attack) alongside a personal one
`ensure_character_magic_check_type` synthesizes per `CharacterSheet`. `magic.ritual`
holds staff/lore rituals alongside a player's personal anima ritual. De-registering
either table was never an option — staff authoring of check types and rituals has to
keep exporting — so the export needed a filter finer than the model.

## Decision

**`CONTENT_MODELS` stays the model-level line (ADR-0168 unchanged).** Two additive
mechanisms carve out the two gaps above, both inside `CONTENT_MODELS`-registered
models:

1. **Code-required rows are declared, not implicit.**
   `world.seeds.config_prerequisites.CONFIG_PREREQUISITES` (`dict[str, Callable[[],
   None]]`, shaped like `world.seeds.clusters.CLUSTER_SEEDERS`) is the one place every
   such row is named. Each entry runs **before** the content load
   (`world.seeds.database.load_content_first`), so a lore fixture always wins over the
   code default (`load_entries` upserts), and the rows land outside
   `world.seeds.tests.test_no_content_slop`'s measurement window — that guard snapshots
   between the content load and the cluster loop, so a prerequisite that ran earlier was
   never eligible to trip it. Registering a helper here does not stop its existing
   gameplay call site from calling it too — every registered helper stays idempotent and
   is the self-healing path if a row is later deleted. Fatigue's prerequisite creates its
   missing stat `Trait` rows too (`FATIGUE_TRAIT_DEFAULTS`), matching the existing
   `world.magic.seeds_cast` precedent, rather than skipping when a trait is absent — the
   check breaks without the trait exactly as it breaks without the CheckType. Fury's
   prerequisite is registered like every other entry and ensures its CheckType row,
   but deliberately does not create a missing `Trait`, because its trait name is
   `FuryConfig.check_trait` — a DB-configurable column, not a code literal — so the
   "named by a string literal in code" rule that justifies auto-creating a `Trait`
   does not reach it.

2. **Per-player rows are excluded from export by a real owner column, never a name
   pattern.** `checks.checktype` gained `owner_sheet` (nullable FK to
   `CharacterSheet`, `related_name="owned_check_types"`, migration
   `0028_checktype_owner_sheet`) — NULL means staff/lore-authored, set means the row
   belongs to that one character. `core_management.content_export.EXPORT_FILTERS`
   (`dict[str, dict[str, object]]`, applied via `queryset.filter(**kwargs)` on top of the
   `CONTENT_MODELS` allowlist) is the row-level export boundary: `magic.ritual` filters
   `author_account__isnull=True`, `checks.checktype` filters `owner_sheet__isnull=True`,
   `checks.checktypetrait` filters on its parent check type's `owner_sheet`. Plain
   filter-kwargs rather than `django.db.models.Q`, deliberately: `content_export.py`
   promises to import cleanly without Django configured, and every predicate here is a
   single AND-only lookup, so a dict literal needs no Django import at module scope at
   all — an OR/NOT predicate must switch to `Q`, imported *inside*
   `export_to_content_repo`, never bolted on as an extra dict key (`filter(**kwargs)`
   ANDs every key together silently, which is the same wrong-but-running failure class
   this whole mechanism exists to close).

## What this rejects

**De-registering the whole table.** Pulling `checks.checktype` or `magic.ritual` out of
`CONTENT_MODELS` to solve the per-player-row leak would also stop exporting every
staff-authored check type and ritual — throwing out real content to fix a boundary
problem one row deep.

**Name-pattern exclusion** (e.g. skip any `CheckType` whose name starts with `"Magic
Check — sheet "`) instead of a real owner column. A pattern match is exactly the failure
this ADR closes: rename the pattern, change the prefix, or add a second synthesis site
with different naming, and the excluded rows silently start exporting again with no
error and no test catching it. A FK column is checked by the database, not
re-derived from a string every time.

**A `CONTENT_MODELS`-write pre-commit linter.** Designed, then cut: a wrong registration
is self-healing (the seeder or code that needs the row recreates it on next use — see
ADR-0168's own de-registration fix for the three pk-keyed singletons) and low-consequence
compared to the cost of another linter surface to maintain.

**Rewriting all 19 modules' `_ensure_*` helpers to raise instead of create.** Same
rejection logic as the linter: the existing helpers are idempotent and harmless exactly
because they create-if-missing; forcing every one of them to fail loudly instead would
convert a self-healing dependency into a hard boot-time coupling for no benefit — the
actual bug this issue fixes was an *undeclared* dependency, not a *silently-repaired*
one.

Related: ADR-0168 (amended here), ADR-0142 (the content-vs-config boundary this
sharpens further). Issue #2724; the sanctum per-resonance capability-name case
(`world/ships/battle_bridge.py:101`) was evaluated against this rule and deliberately
left unregistered — those names are derived from `Resonance` rows at runtime, not a
fixed literal, so there is nothing to declare; filed as #2736 (`needs-design`).

> Status: accepted · Source: issue #2724
