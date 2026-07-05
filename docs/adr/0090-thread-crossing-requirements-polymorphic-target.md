# ADR-0090: Thread crossing requirements reuse the progression requirement family via a polymorphic unlock target

## Status

Accepted

## Context

#1885 needs a way to gate thread-level advancement across PathStage crossing
levels (3, 6, 11, 16, 21) in the Rite of Imbuing (`spend_resonance_for_imbuing`)
on authored requirements — items, achievements, traits, etc. This is the
gating twin of the already-built resonance-based reward side (variant
discoveries, signatures).

The progression app already has a requirement family: 8 concrete requirement
types (`TraitRequirement`, `ItemRequirement`, `AchievementRequirement`, etc.)
that subclass `AbstractClassLevelRequirement` and attach to a
`ClassLevelUnlock` via a NOT NULL `class_level_unlock` FK. These are checked
by `check_requirements_for_unlock()` during the Ritual of the Durance and
Audere Majora crossings.

ADR-0089 established that a new requirement *type* needing item
possession-checking in a third domain would add its own sibling model. The
distinguishing axis in ADR-0089 was **consumption semantics**:
`RitualComponentRequirement` is *consumed* on ritual performance, while
`ItemRequirement` is *possession-only*. Thread crossings are possession-only
too — no item is consumed when a crossing requirement is satisfied.

## Decision

**Option A — new `ThreadCrossingThreshold` authored catalog row** mirroring
`ClassLevelUnlock`, keyed on `(target_kind, level)`. Requirements FK to it.

The existing `AbstractClassLevelRequirement` base is generalized to
`AbstractUnlockRequirement` with a **polymorphic unlock target**: the
`class_level_unlock` FK is made nullable, a new `thread_crossing_threshold`
nullable FK is added, and a CheckConstraint enforces exactly one is set. All
8 concrete requirement types inherit the base unchanged — no per-subclass
duplication.

This follows **ADR-0016** ("one shared base per concept"): the requirement
family is one concept (possession/threshold gating); the unlock target is
polymorphic. The distinguishing axis in ADR-0089 (consume vs. possess) does
not split Durance from thread crossings — both are possession-only — so
ADR-0016's convergence rule applies rather than ADR-0089's sibling-per-domain
rule.

### Per thread-kind scoping

The catalog is keyed on `(target_kind, level)` so a level-3 GIFT crossing
can require different things than a level-3 COVENANT_ROLE crossing.
`target_kind` is the `Thread` discriminator (TRAIT/TECHNIQUE/FACET/
RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE/COVENANT_ROLE/GIFT/MANTLE/SANCTUM).

### Fail-open runtime contract

If no `ThreadCrossingThreshold` row exists for `(target_kind, level)`, no
gate fires — the imbuing loop advances through the crossing unimpeded. This
mirrors Durance's `ClassLevelUnlock.DoesNotExist` → no gate behavior.

### Possession-only semantics

Items are retained when a crossing requirement is satisfied (mirrors #1859
Decision 4 + ADR-0089). No consumption plumbing is added to the imbuing loop.

## Consequences

- The `AbstractClassLevelRequirement` rename to `AbstractUnlockRequirement`
  is mechanical; a backwards-compat alias
  (`AbstractClassLevelRequirement = AbstractUnlockRequirement`) is kept for
  any external references.
- The migration is additive: existing rows keep `class_level_unlock` set and
  `thread_crossing_threshold` null, so the CheckConstraint is satisfied.
- `check_requirements_for_unlock()` is refactored: the shared loop is
  extracted into a `_check_requirements(target, fk_name)` helper, and a new
  `check_requirements_for_thread_crossing(character, threshold)` wrapper
  filters on the `thread_crossing_threshold` FK.
- The imbuing loop gains a crossing gate after the XP_LOCK check and before
  the cap check. Crossing levels (3, 6, 11, 16, 21) never coincide with
  10-multiples, so ordering between XP_LOCK and CROSSING_REQUIREMENT is
  academic — but XP_LOCK first keeps existing test expectations stable.
- A crossing block is a *soft* block: resonance is spent, levels below the
  crossing are gained, but the level doesn't cross. `ThreadImbueResult`
  gains `"CROSSING_REQUIREMENT"` to its `blocked_by` Literal and a new
  `blocked_requirement_messages: list[str]` field. `ImbueAction` returns
  `success=True` (matching the XP_LOCK precedent) with a message explaining
  the block.
- Reward expansion for non-variant thread kinds (TRAIT, FACET, MANTLE,
  SANCTUM, RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE) is a separate
  follow-up issue. The `is_crossing_level` helper built here is reusable by
  that future work.
