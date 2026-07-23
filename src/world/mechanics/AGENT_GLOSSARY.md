# Mechanics glossary

**ModifierCategory**:
A broad grouping for modifier targets (stat, magic, affinity, resonance, goal). A cached lookup table that organizes the unified target registry for display and filtering.
_Avoid_: modifier group, modifier kind

**ModifierTarget**:
A single entry in the unified registry of everything that can be modified — one row per stat, capability, check type, damage resistance, resonance, or goal domain. Replaces the former separate Affinity/Resonance/GoalDomain models; optional FKs link it to the concrete trait, capability, check type, or damage type it represents.
_Avoid_: modifiable, affinity/resonance (as separate models), attribute

**ModifierSource**:
The provenance record for a character's modifier — where it came from (e.g. a distinction effect template plus the character-distinction instance). It answers WHICH target a modifier grants and its base value, and drives cascade cleanup when the source is removed.
_Avoid_: origin, provider, grantor

**CharacterModifier**:
A materialized modifier value on a character (`value`, `source`, optional `expires_at`) for fast lookup. All modifiers for a given target stack (values sum); zero-value rows are hidden from display. Its target is derived from the source, stored directly for efficient queries.
_Avoid_: stat bonus, buff value, character stat row

**ConsequenceEffect**:
A structured mechanical effect applied when a consequence is selected (typed `effect_type` with validated fields, ordered execution). All mechanical outcomes must be such structured primitives — GMs pick pre-authored consequences and never freehand effects; `mechanical_description` is display flavor only.
_Avoid_: outcome, result effect, freeform effect

**Property**:
A neutral descriptive tag on a target or environment describing what something IS, not what can be done to it (flammable, locked, magical, frozen). Grouped under a `PropertyCategory`.
_Avoid_: trait, flag, tag (generic), attribute

**ObjectProperty**:
A runtime attachment of a `Property` to a specific game object — the instance binding that gives an individual object its descriptive tags.
_Avoid_: object flag, object tag, attribute row

**PropertyDetonation** (#2210):
A `Property`'s one-shot detonation sidecar (OneToOne) carrying a `consequence_pool` to
fire against everyone positioned at the object's `Position` when it goes off. Marks the
`Property` — not an individual object — as "the kind of thing that can detonate";
whether a *specific* object actually can is a separate question (see **Volatile**,
below). Mirrors how `room_features.Trap.consequence_pool` is declared.
_Avoid_: detonation profile, blast config, explosion template

**Volatile** (#2210):
Said of a game object carrying an `ObjectProperty` whose `Property` has a
`PropertyDetonation` row (`world.mechanics.services.volatile_object_property`).
Redirecting a guardian's saved damage into a volatile object (`world/combat/
AGENT_GLOSSARY.md`'s **Redirect**) fires its `PropertyDetonation.consequence_pool`
against every combatant at the object's `Position`, then deletes the triggering
`ObjectProperty` — the volatility is spent, not reusable. An object with no `Position`
is never volatile in practice for redirect purposes (position-anchored only, no
room-wide fallback).
_Avoid_: explosive, detonatable (prefer "volatile" as the canonical adjective), primed

**Approach**:
A way to resolve a challenge (`ChallengeApproach`), connecting what a character can do (an `Application`) with how it is rolled (a `CheckType`) for a specific challenge template, optionally gated by a required effect property.
_Avoid_: method, tactic, option, resolution path

**World-interaction template** (#2503):
A `ChallengeTemplate` wired onto an `Application.default_template` — the curated,
authored resolution content (approaches, check type, consequence pool) a bare-object
affordance mints into a real `ChallengeInstance` the moment a player acts on it. A null
`default_template` is the deliberate default: most Applications never grant ambient
world presence outside a GM-staged Situation.
_Avoid_: default template (ambiguous — say which model it's a default *for*), ambient
challenge

**Bare-object affordance** (#2503):
An `AvailableAction` synthesized by `get_available_actions`'s second source
(`_bare_object_actions`) straight from an `ObjectProperty` match — no authored
`ChallengeInstance` exists until the player dispatches it (via the `WORLD_INTERACTION`
action backend, which mints one lazily). See ADR-0147.
_Avoid_: object action, environmental action, ambient action

**SituationTrapLink**:
An authored trap blueprint carried by a `SituationTemplate` — name, consequence
pool, detect/disarm check types and difficulties, hidden/obvious default.
Materialized into a real `room_features.Trap` row by `instantiate_situation`;
carries no runtime state (no armed/detected/position — those are fresh per
instantiated Trap).
_Avoid_: trap template, trap blueprint (as a class name), situation trap

**SituationChallengeLink.target_object_name** (#1895):
The authored display name for the ObjectDB `instantiate_situation` auto-creates
to embody a Situation-carried Challenge (e.g. "the locked door"). Player-visible
via `ChallengeInstanceSerializer.target_object_name`. Not to be confused with an
actual room prop — the object exists solely as the Challenge's mechanical anchor.
_Avoid_: target prop, challenge prop, door object (as a literal expectation)

**Common ModifierTargets** (the "is X a stat?" answer — they're targets, not Traits):
Recurring named axes accumulate as `ModifierTarget` rows (category `roll_modifier`),
totalled via `mechanics.services.get_modifier_total(sheet, target)`. Canonical rows:
- **allure** — social hotness; feeds attraction conditions (`world/seeds/social_relationships.py`,
  Attractive distinction ranks grant it) and any "how good do they look" read
  (e.g. NPC reaction-line bands, `npc_services.reactions`).
- A fear-facing sibling (intimidation-check analogue of allure) is ruled-but-unnamed;
  when ApostateCD names it, seed it the same way and list it here.
Bare/unknown `ModifierSource` rows contribute NOTHING to totals (#909) — grants must
ride a recognized source (distinction effect, achievement reward, comfort, equipment).
_Avoid_: inventing an "Allure" Trait/skill row; it is a modifier target.
