# Companions

Generic bound-creature substrate (#672) plus one concrete consumer: a
Beastlord-style Gift that lets a PC bind a wild beast archetype as a
persistent, room-present companion.

## Models (`world.companions`)

- `CompanionArchetype` — staff-authored catalog row (`domain`, `name`,
  `description`, `bind_difficulty`, `capacity_cost`). Binding is
  archetype-selection: no discrete in-room "wild creature" object is required.
- `Companion` — the bound instance (`owner` → `CharacterSheet`, `archetype`,
  `granting_gift` → `magic.Gift`, `name`, `objectdb` → live `CompanionObject`,
  `bonded_at`/`released_at`). Never hard-deleted.

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

## API

`world.companions.views.{CompanionViewSet, CompanionArchetypeViewSet}` —
read-only, mounted at `/api/companions/` (`companions` and
`companion-archetypes` router routes). Binding happens via the Action
dispatch seam, not a ViewSet write.

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
- Combat participation (`CombatOpponent` ally / `BattleVehicle` bridge).
- Enthralling/dominating an existing full-Persona NPC or PC (`needs-design`) —
  also needs the delegated-consent extension above.
- Other domains (necromancer, elemental, construct, spirit) reusing this
  substrate — future Path/Gift content work.
