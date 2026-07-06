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

`actions.definitions.companions.ReleaseCompanionAction` (`release_companion`
key, #1918) — releases a bonded companion: destroys its live object, sets
`released_at`, keeps the row. Reuses `_resolve_owned_companion` for
ownership + active validation (mirrors `CompanionFightAction`/
`DeployCompanionAction`).

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
