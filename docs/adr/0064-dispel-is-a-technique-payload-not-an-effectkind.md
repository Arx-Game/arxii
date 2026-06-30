# Dispel is a technique payload row, not an EffectKind (thread-pull) entry

Issue #1585 ("Dispel / cleanse: remove a condition via a technique") asks for a player-castable
dispel. The obvious reading of "add a REMOVE effect kind" is to extend `EffectKind`
(`world/magic/constants.py`) — but that enum is the **thread-pull effect axis**: its members
(FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS, …) live on `CombatPullResolvedEffect` and are
**per-round pull-declaration modifiers** a *Thread* adds to a cast/clash. They are not authored
onto a `Technique`, and they are gated by thread level. A dispel that only fires when a specific
thread is pulled — and only in combat — is the wrong shape for "a player casts Cleanse on an
ally."

Dispel is a **castable technique**, so it is modeled as a technique payload row mirroring the
existing apply path: `TechniqueRemovedCondition` (subclass of `AbstractAppliedCondition`,
sibling to `TechniqueAppliedCondition`), resolved through `remove_technique_conditions` — the
removal sibling of `apply_technique_conditions` — wired into the same cast seam
(`request_technique_cast` / the combat resolver). This reuses the proven player-facing path:
every other magical effect reaches players as a cast technique, not a thread pull, and the budget
builder / draft workbench / admin / serializer all extend naturally from the apply row's shape.

The removal payload **diverges** from the apply row in one place: it carries `target_kind` and
`minimum_success_level` as **authored fields**. The apply path hardcodes these (ENEMY / 1 via
model defaults) and never exposes them to authors, but a dispel technique must support SELF
(cleanse) and ALLY (ally-debuff-strip) targeting, so removal authors them explicitly. (This does
not backport target_kind authoring to the apply path — only removal.)

The dispel honors the three `ConditionTemplate` fields that were **already built but read by
nothing**: `can_be_dispelled` (hard gate — `False` is a no-op, never an error), `cure_check_type`
(when set, an opposed `perform_check` is rolled; `success_level > 0` removes, else resisted), and
`cure_difficulty` (the opposed check's `target_difficulty`). Wiring pre-existing fields — rather
than adding new dispel-specific ones — keeps the data model honest: those fields were authored for
exactly this and were dormant only because no dispel effect existed to honor them.

**Out of scope (deliberate):** the `TechniqueVariant` specialization layer has no
`TechniqueVariantRemovedCondition` and `_ResolvedTechnique` exposes no `removed_conditions`
accessor. `resolve_specialized_variant` is not on the live cast path today (covenant services +
tests only), so a dispel authored on a base technique reads correctly via the parent. This is the
same latent gap the apply path already has; if variant resolution reaches the cast path, both the
apply and removal accessors must be added together. Documented here so it is not mistaken for an
oversight.

> Status: accepted · Source: issue #1585
