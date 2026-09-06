# Companions

Generic bound-creature substrate (#672) plus one concrete consumer: a
Beastlord-style Gift that lets a PC bind a wild beast archetype as a
persistent, room-present companion.

## Models (`world.companions`)

- `CompanionArchetype` — staff-authored catalog row (`domain`, `name`,
  `description`, `bind_difficulty`, `capacity_cost`, `is_mount` — whether the
  archetype is ridable, #1843). Binding is
  archetype-selection: no discrete in-room "wild creature" object is required.
- `Companion` — the bound instance (`owner` → `CharacterSheet`, `archetype`,
  `granting_gift` → `magic.Gift`, `name`, `objectdb` → live `CompanionObject`,
  `bonded_at`/`released_at`, `ridden_by` — nullable unique FK →
  `CharacterSheet`, #1843, see "Mount riding" below). Never hard-deleted.

## Companion Capacity

Computed from the granting Gift's `Thread.level` via the existing
`ThreadPullEffect` mechanism (`TargetKind.GIFT`, `EffectKind.FLAT_BONUS`,
tier 0) — see `world.companions.services.companion_capacity`/
`used_companion_capacity`. No new enum values were added to the magic system.

## Room presence

`typeclasses.companions.CompanionObject` extends `Character` (see
ADR-0088). A new `Character.companions` cached-property handler
(`world.companions.handlers.CharacterCompanionHandler`) exposes a PC's active
companions; `Character.at_post_move` moves each active companion's
`objectdb` to the owner's new location (`quiet=True`) so companions follow
their owner between rooms. `CompanionObject.at_post_move` itself overrides
`Character.at_post_move` to skip the narrative-agent side effects (mission
triggers, trap detection, fame reactions, clue triggers, sunlight exposure,
resonance-alignment reconciliation) that assume a real story participant —
a companion arriving in a room shouldn't spring any of them.

## Binding

`actions.definitions.companions.BindCompanionAction` (`bind_companion` key) —
gated by `HasCompanionCapacityPrerequisite`, executes via the existing
`perform_check` primitive against `CompanionArchetype.bind_difficulty`.

`actions.definitions.companions.ReleaseCompanionAction` (`release_companion`
key, #1918) — releases a bonded companion: destroys its live object, sets
`released_at`, keeps the row. Reuses `_resolve_owned_companion` for
ownership + active validation (mirrors `CompanionFightAction`/
`DeployCompanionAction`).

## Mount riding (#1843)

A mount is a `Companion` whose archetype has `is_mount=True` — no separate
model or typeclass. `world.companions.services.mount_companion(sheet,
companion)` validates ownership, `is_active`, `archetype.is_mount`, a live
`objectdb`, and that neither side is already mounted/ridden (`Companion
.ridden_by` is a nullable **unique** FK → `CharacterSheet` — one rider per
mount, enforced at the DB level), then sets `ridden_by` and applies the
seeded "Mounted" `ConditionTemplate` (`world.companions.mount_content
.ensure_mount_conditions`) to the rider. `dismount_companion(sheet)` is the
inverse. Both raise `MountError` (a `user_message`-carrying exception,
mirroring `CompanionOrderError`) on failure.

Mounted carries **no passive check bonus** — it exists purely to gate two
combat maneuvers (see the Combat system doc's "Mounted combat" entry):
`CombatManeuver.CHARGE` (mounted charge into a normal attack, flat
check/damage bonuses doubled for an equipped `GearArchetype.LANCE`) and
`CombatManeuver.JOUST` (a mounted, lance-armed opposed pass, DUEL-only,
2 participants, both sides Mounted + LANCE-equipped). A joust's decisive
loss applies the seeded "Unhorsed" condition and force-dismounts the loser
directly (no reactive trigger needed — the resolver already holds both
sheets).

Three dismount triggers: voluntary (`companion dismount`), encounter exit
(`LeaveEncounterAction` force-dismounts on leaving combat), and companion
defeat (`resolve_companion_defeat`'s die outcome routes through
`release_companion`, which force-dismounts the rider before releasing the
companion).

Telnet: `companion mount <name|id>` / `companion dismount` (`CmdCompanion`,
`commands/companion.py`) dispatch `MountCompanionAction`/
`DismountCompanionAction` (`actions/definitions/companions.py`) on the same
REGISTRY seam every other companion verb uses.

## Companion emote (#3294)

Companions are characters, not turrets: an owner can pose *as* their bonded
companion in a social scene. `Interaction` (`world.scenes`) gains a nullable
`attributed_companion` FK -> `companions.Companion` (migration
`0163_interaction_attributed_companion`) — cosmetic feed attribution only.
`Interaction.persona` stays the companion's owner in every case, so block/
mute/consent/moderation all key on the same field they always have; the
attribution FK never substitutes for authorship (see the Scenes doc's
"Companion attribution" entry for the pipeline-side detail).

`actions.definitions.companions.CompanionEmoteAction` (`companion_emote`
key) — gated by `CompanionPresentPrerequisite` (owned by the actor, active,
AND co-located: `companion.objectdb.location == actor.location`). Presence
is usually automatic — `Character.at_post_move` already moves a PC's active
companions along with them (see "Room presence" above) — but the gate stops
a ghost-pose if a companion was ever left behind. Delivery is POSE-level,
same convention as `PoseAction`: the player writes the companion's own name
into the pose text (no auto name-prepend).

Telnet: `companion emote <name|id> <text>` (`CmdCompanion`). Web: `POST
/api/companions/companions/{id}/emote/` (see the Write endpoints table
below) plus a composer "as `<companion>`" toggle (`CompanionSelector.tsx`,
pattern-mirrors `LanguageSelector.tsx`) shown only when `CompanionSerializer
.is_present` is true for at least one bonded companion — never offered for
an absent one.

## Bond with the owner (#3575, ADR-0272)

A companion has no `CharacterSheet`, so the owner's bond toward it is a
`CharacterRelationship` whose `target_companion` points at the `Companion` row
(`target` is null on such rows). Only the bonded owner may hold one and it is active
from creation; writes toward a released companion are refused, and the rows survive
release (the `Companion` row is never hard-deleted). All four relationship verbs accept
the companion target on web (`target_companion_id`) and telnet (the companion's name).

In an escalating encounter, the companion's ALLY `CombatOpponent` reaching `DEFEATED`
emits `CHARACTER_INCAPACITATED`, and the owner surges once (`ALLY_FALLEN`) when their
relationship has a `fuels_escalation_spikes` track at or above the curve's
`spike_minimum_track_points`. The peril leg is inert for companions (no opponent peril
band). `resolve_companion_defeat` (#1873 Decision 4) still has no production caller;
wiring it at encounter end is a separate follow-up.

## API

`world.companions.views.{CompanionViewSet, CompanionArchetypeViewSet}` —
mounted at `/api/companions/` (`companions` and `companion-archetypes`
router routes). Read endpoints are read-only; write endpoints converge on
`action.run()` via `PuppetActorMixin` (same pattern as `SanctumViewSet`).

### Write endpoints (#1918)

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/api/companions/companions/bind/` | POST | `{archetype_id, gift_id, name}` | `{companion_id}` (201) / `{detail}` (400) |
| `/api/companions/companions/{id}/release/` | POST | — | `{}` (200) / `{detail}` (400) |
| `/api/companions/companions/{id}/fight/` | POST | — | `{opponent_id}` (200) / `{detail}` (400) |
| `/api/companions/companions/{id}/deploy/` | POST | — | `{vehicle_id}` (200) / `{detail}` (400) |
| `/api/companions/companions/{id}/emote/` | POST | `{text}` | `{}` (200) / `{detail}` (400) |

Detail-level endpoints (`release`/`fight`/`deploy`) scope the companion via
`get_queryset` (the caller's active companions); a foreign companion returns
404. The Action's `_resolve_owned_companion` re-validates ownership — defense
in depth, and keeps the Action usable from telnet where the id comes from text.

## Player surfaces

### Telnet (`companion` command, #1918)

`commands.companion.CmdCompanion` (`companion` key) — a `DispatchCommand`
routing subverbs through `dispatch_player_action` (the same REGISTRY seam the
web uses). Mirrors `CmdSanctum`.

```
companion                             — status hub (active companions + capacity)
companion status                      — (same)
companion list                        — (same)
companion bind archetype=<name|id> gift=<name|id> name=<text>
companion release <name|id>
companion fight <name|id>             — requires active encounter
companion deploy <name|id>            — requires active battle
companion emote <name|id> <text>      — pose as a bonded, present companion (#3294)
```

`name=` must be the final token on `bind` (it greedily consumes the rest of
the line so names with spaces work).

## Consent-delegation (governing principle, not built)

An action requiring consent that targets a companion should route that
consent to the companion's **owner**, not the companion itself (it has no
account/Persona to ask). Nothing in this PR creates such an interaction
(hostile/behavior-altering technique-targeting is part of the deferred combat
work), so no code exists for this yet — `SceneActionRequest` only supports
target == consenter today. Build this alongside the combat-participation
follow-up, not before there's a real consumer.

## Deferred (see #672 issue body for the full list)

- NPCAsset informant/contact promotion mechanic (separate follow-up issue).
- Combat participation mechanics — the player surface now exists (`companion
  fight`/`companion deploy` + web `fight`/`deploy` endpoints, #1918), bridging
  companions into encounters/battles via `CompanionFightAction`/
  `DeployCompanionAction`. The deeper combat-participation logic (targeting,
  companion orders, round-by-round control) remains future work.
- Enthralling/dominating an existing full-Persona NPC or PC (`needs-design`) —
  also needs the delegated-consent extension above.
- Other domains (necromancer, elemental, construct, spirit) reusing this
  substrate — future Path/Gift content work.
