# Redirect destination is declared, not improvised

A REDIRECT-flavor guardian (Mirror Ward-style reflection, #2210) picks the saved
damage's destination — away / a named enemy / a named volatile object — at
**declaration time** (`declare_interpose`, stored on `CombatRoundAction`), matching
ADR-0032's predefined-menu shape rather than letting the player improvise a target
once the blow actually lands. Grading stays tri-level (clean/partial/fail via the
shared `_grade_interpose_damage`, ADR-0060's mutation-only pattern — zero the payload,
then re-apply the saved amount with `bypass_pre_apply=True` to avoid a reflect↔reflect
loop) and every destination degrades to "away" (the universal fallback) if it's no
longer valid at resolution time — the enemy defeated, the object moved or already
detonated. `redirect_opponent_target` is a `CombatOpponent` FK, never `CombatParticipant`
— redirecting saved damage onto a fellow PC is structurally impossible (ADR-0023's
express-invariants-structurally spirit, not a runtime guard). Volatile-object
detonation is one-shot: the triggering `ObjectProperty` row is deleted after its
`PropertyDetonation.consequence_pool` fires, and it only fires at combatants
positioned at the object's own `Position` — no room-wide fallback when the object
has none. We rejected **fire-time destination choice** (prompting the guardian to pick
a destination only once the block lands, mid-resolution): it would require a paused,
two-phase interpose resolution (grade now, prompt-and-wait, then apply), adding a
second round-trip and a new pending-offer model for a maneuver that already commits at
declaration under #2207's existing shape — and it breaks the "the interpose IS the
commitment" invariant every other interpose flavor (barrier, blink) already relies on.

> Status: accepted · Source: issue #2210 · Confidence: built & tested (
> `world/combat/tests/test_redirect_resolution.py`, `actions/tests/
> test_combat_maneuvers.py::InterposeRedirectDispatchSeamTest`)
