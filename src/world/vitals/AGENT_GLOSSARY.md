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

**Certain death (deferred)** (#4098):
A death that would otherwise be immediate but is held until a narratively appropriate
moment ends, so the character keeps acting through the decisive beat instead of dying
mid-action. Soulfray's `character_loss` consequence is the first (and currently only)
source: under an active `death_deferred` condition (Audere, Audere Majora) it sets
`CharacterVitals.death_certain_pending` via `defer_or_apply_certain_death` instead of
killing synchronously. Resolved by `apply_pending_certain_death` from the existing
condition-expiry seam when the LAST deferring condition ends - ordinarily the
encounter's close - backstopped at encounter cleanup; both the defer and the
resolution honor story protection. Soulfray itself can only ever reach a
`character_loss` consequence inside a combat encounter - a scene cast, a social
action, a battle, or an out-of-combat reactive spend is always non-lethal. A dispel
that removes the deferring condition mid-fight resolves the pending death right then,
not at the encounter's end - deferral is tied to the condition's lifetime, not the
encounter's.
_Avoid_: pending death (ambiguous with the pre-existing `death_deferred_pending`
CHARACTER_KILLED-suppression flag, a different mechanism), scheduled death.
