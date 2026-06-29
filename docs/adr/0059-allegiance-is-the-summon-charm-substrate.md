# Allegiance is the unified substrate for summons and future charm/switch-sides

A summoned ally and a charmed/switched-sides foe are the same abstraction: a
`CombatOpponent` whose side has changed. We implement this with a single mutable
`CombatOpponent.allegiance` field (`CombatAllegiance.ENEMY` default / `ALLY`),
rather than a separate `SummonedAlly` model or parallel companion system (rejected:
parallel implementations violate ADR-0016). `CombatOpponent.summoned_by` (FK →
`CharacterSheet`) + `bond_expires_round` carry the conjurer bond so the summon is
cleaned up at round expiry; the same two fields are inert on a charmed opponent
(bond fields are nullable). To enable ally-vs-enemy damage, `CombatOpponentAction`
gains an `opponent_targets` (M2M → `CombatOpponent`) relation populated by
`select_npc_actions` for ALLY summons and resolved by
`_resolve_npc_action_on_opponent_target` through `apply_damage_to_opponent`,
bypassing the PC survivability pipeline. `combatants_hostile_to` returns the
appropriate enemy set by querying on allegiance, so allegiance-aware victory,
targeting, and AoE all follow from the same mutable field. This design also folds
in #672 (in-combat companion) and is the intended substrate for #1590
(charm/switch-sides), which is a future `allegiance` flip on an existing ENEMY
opponent with no new model needed.

> Status: accepted · Source: issue #1584 · Confidence: built & E2E-tested (
> `integration_tests/pipeline/test_summon_e2e.py`); `CombatOpponent.allegiance/
> summoned_by/bond_expires_round`; `CombatOpponentAction.opponent_targets` (
> combat/0023 migration)
