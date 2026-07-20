# ADR-0108: Vows as combat roles — three pillars of vow-driven power

## Status

Superseded by ADR-0149 (#2529) — the single `CovenantRole.archetype` enum this ADR's
three pillars keyed off of is replaced by a SWORD/SHIELD/CROWN weighted blend
(`sword_weight`/`shield_weight`/`crown_weight`, `blend_weight_for(axis)`). The
**stat pillar** (`VowStatScaling`/`vow_stat_scaling_bonus`) is unaffected and stays
live. The **gear pillar** (`VowGearScaling`/`vow_gear_scaling_bonus`) is
short-circuited to 0 pending ADR-0149's Layer 3 (#2533). The **technique pillar**
(`ArchetypeActionScaling`) is replaced by `CovenantRoleActionScaling`
(per-role, not per-archetype) plus a new always-on blend power term
(`covenant_role_blend_power_term`) for `cast_technique`. See ADR-0149 for the
four-layer model this collapses into. The role-source variant resolution and
capability-grant-wiring decisions below are unaffected and remain accurate.

Accepted — 2026-07-09

## Context

Issue #2022 specifies that a character's covenant vow is the primary axis of
their combat power, not a bonus or label. Three pillars: (1) stat power
scaling with the COVENANT_ROLE thread level, (2) equipment effectiveness
scaling, (3) role-granted techniques that specialize at crossings. The
initial PR (#2106) shipped only the structural foundation (models + engage/
disengage wiring + combo archetype gate). The completion work adds the three
power pillars, the archetype action scaling, the role catalog seed, and the
enhancement technique logic.

## Decision

**VowStatScaling** — a new model keyed by `(covenant_role, modifier_target)`
with `bonus_per_level` scaling by the COVENANT_ROLE thread level (not
character level, which `CovenantRoleBonus` already handles). Wired into
`equipment_walk_total` as an additive component alongside the existing
`covenant_role_bonus` and `covenant_level_bonus`. Derive-on-read; no
`CharacterModifier` rows persisted. When the vow dims (#2051), the engaged
flag drops and the scaling returns 0.

**VowGearScaling** — a new model keyed by `(gear_archetype, role_archetype)`
with a `thread_level_multiplier`. For each equipped item, the bonus is
`int(gear_stat * thread_level * multiplier)` — the vow amplifies how much
the gear contributes. Wired into `equipment_walk_total` alongside the stat
scaling. When the vow dims, the equipment's contribution reverts to base.

**ArchetypeActionScaling** — a new model keyed by `(action_key, role_archetype)`
with a `thread_level_multiplier`. Read by `archetype_action_scaling_bonus()`
at the combat action resolution seam. SHIELD roles scale the interpose
partial-block damage reduction; SWORD roles add a flat power bonus to
`cast_technique` via a power term provider; CROWN roles scale rally actions.

**Role-source variant resolution** — `resolve_specialized_variant` accepts
an optional `character_technique` parameter. When the `CharacterTechnique`
has a `role_source` FK, the resolver reads the COVENANT_ROLE thread level
instead of the GIFT thread level — so a role-granted technique specializes
by the vow's depth, not the personal gift's depth.

**Enhancement overlap** — a technique with `enhances_effect_type` set gains
a flat power bonus when the character also has a technique whose
`effect_type` matches. This is a power term provider (`enhancement_overlap_term`)
that checks for overlap and returns a fixed bonus. The enhancement is a rider,
not a replacement — a well-matched vow amplifies existing kit.

**Capability grant wiring** — `CovenantRole.granted_capabilities` M2M is read
directly by `passive_capability_grants()` in `handlers.py`. The stub functions
in `covenants/services.py` are correct no-ops: the handler reads the M2M
alongside the existing `ThreadPullEffect`-based capability grants. The
`_announce_capability_diff` path already fires before/after engagement, so
the diff correctly surfaces gained/lost capabilities.

## Consequences

- Two new queries added to `equipment_walk_total` (one per scaling model) when
  the character has engaged roles. The query budget test is updated from 8
  to 10.
- The `resolve_specialized_variant` signature gains a `character_technique`
  parameter (default `None`), backward-compatible with all existing callers.
- The cast pipeline (`cast_services.py`) now looks up the `CharacterTechnique`
  at the variant resolution call site to pass provenance through.
- The role catalog seed (`seed_role_catalog_content`) runs after items + magic
  in the cluster seeder, attaching granted gifts, capabilities, and archetype
  scaling to the three canonical role rows.
