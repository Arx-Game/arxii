# Vitals glossary

**Survivability pipeline**:
The damage-consequence chain (`process_damage_consequences`): permanent-wound check, death check (applies Bleeding Out, never instant death), knockout check (applies Unconscious). Each tier rolls an authored consequence pool; a missing pool no-ops the tier.
_Avoid_: damage pipeline, death system (for the whole chain)

**Wake arc** (#2287):
An unconscious character's recovery loop: one Endurance check per round (`attempt_wake`), difficulty scaled to injury and easing per round and with healing, with a guaranteed-wake deadline (`ConditionInstance.expires_at`) as the ceiling. The benign mirror of Bleeding Out's staged resists.
_Avoid_: recovery timer, KO timer

**Dreamside** (#2287):
Where an unconscious character's perception goes: the liminal dream room replaces their room view and they miss room broadcasts. The dead are never dreamside — a ghost watches the waking room. The dream realm proper (#2290) replaces the placeholder room.
_Avoid_: blackout, unconscious screen

**Ghost interlude** (#2287, ADR-0131):
The span between death and retire: the player keeps the puppet as a spectator (full perception, OOC/channels), IC verbs whitelisted (`DEAD_ALLOWED_ACTION_KEYS`), emit/pose bounded to recognized containers (death scene while active, IC day of death; funerals #2289 and seances #2290 later).
_Avoid_: ghost mode, afterlife (for the OOC state)

**Retire** (#2287):
The release that ends the ghost interlude: `retire_character` sets `CharacterVitals.retired_at`, the final lock — the character can never be puppeted again. Player-fired, staff-forceable (offscreen deaths), auto-fired by the `vitals.auto_retire` task after `auto_retire_days`. Distinct from `LifecycleState.RETIRED` (living retirement, undesigned).
_Avoid_: delete, archive, shelve (for the death release)

**Death-kudos** (#2287):
The capped graceful-death earning channel on account kudos: witnesses honor how the player handled the death; scaled grants (GM/staff 50%, participants 5% of lifetime XP spend) aggregate-capped at 100% of lifetime spend, with post-cap trickle floors. Window: death → retire.
_Avoid_: death XP, legacy XP, inheritance
