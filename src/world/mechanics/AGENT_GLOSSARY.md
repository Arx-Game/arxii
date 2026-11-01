# Mechanics glossary

**ModifierCategory**:
A broad grouping for modifier targets (stat, magic, affinity, resonance, goal). A cached lookup table that organizes the unified target registry for display and filtering.
_Avoid_: modifier group, modifier kind

**ModifierTarget**:
A single entry in the unified registry of everything that can be modified — one row per stat, capability, check type, damage resistance, resonance, or goal domain. Replaces the former separate Affinity/Resonance/GoalDomain models; optional FKs link it to the concrete trait, capability, check type, or damage type it represents.
_Avoid_: modifiable, affinity/resonance (as separate models), attribute

**Favor categories** (`favor_invocation`, `favor_earning`, #4333):
The two modifier categories that carry favor with a worshipped being. A `ModifierTarget` in them names its being through `target_being` (a plain FK; one target per being per category); null there means the target applies to any being. `favor_invocation` values are difficulty points eased on an invocation check, `favor_earning` values are percentage points added to the earning rate. Read only by `world.worship.favor_services.favor_modifier_total`; created by `ensure_being_modifier_targets`.
_Avoid_: a being-specific modifier model, "blessing" as a category name

**Maneuver effect** (#4783):
One named part of a combat maneuver with one number, held as a row of the fixed `ManeuverEffect` catalog (`key` unique, `base_value`, staff `notes`; eight rows: Charge to hit 10, Charge damage 5, Charge reach 5, Cover escape bonus 10, Succor partial protection 50, Interpose partial protection 50, Rally morale 15, Rally surge intensity 100). Staff edit a base value in the admin and can neither add nor delete a row; code finds a row by `key`, never by name (`ensure_maneuver_effects`, `get_maneuver_effect`). A character's value for an effect is `effect_value(sheet, key)`: the base plus every modifier on a `ModifierTarget` in the "maneuver_effect" category that is scoped to that effect (`scope_maneuver_effect`) or to its kind (`scope_effect_kind`), summed from distinctions, crafted recipe modifiers on worn items, facet and mantle crossing-choice conditions, vow stat scaling and active conditions (a facet's own flat bonus does not reach an effect). A target with neither scope matches nothing. The value is never below 0, and partial protection never above 100. `effect_modifier_total` is the same sum unclamped, for a caller that scales the base itself (a lance doubles Charge's base only).
_Avoid_: maneuver stat, maneuver tuning, action scaling (the removed vow-only table)

**Effect kind** (#4783):
What sort of number a maneuver effect is (`EffectKind`: to hit, damage, reach, escape bonus, partial protection, morale, surge intensity; and, for technique scopes (#4822), condition severity and condition duration in rounds). A broad target names a kind, such as "partial protection, any maneuver". Each kind fixes the unit of every modifier that targets it, so a modifier on a kind adds the same sort of number wherever it applies. Derived from the key by the `MANEUVER_EFFECT_KIND` map, not stored on the row. A modifier on a maneuver effect is a flat amount; a vow adds its shown thread level times its `bonus_per_level`.
_Avoid_: effect type, effect category (a `ModifierCategory` is the registry grouping, and "maneuver_effect" is one of them)

**Technique scope** (#4822):
A narrowing on a "maneuver_effect" `ModifierTarget` that names the technique it changes: `scope_technique`, `scope_gift`, `scope_technique_function`, `scope_damage_type` or `scope_resonance`. Scopes combine (every one set must match), an unset scope means any, and a technique scope needs `scope_effect_kind` and no `scope_maneuver_effect`; the damage type scope is for the damage kind only. A gift scope matches the technique's gift and that gift's parent, so an umbrella gift reaches its child gifts' techniques. The kinds a technique scope narrows are damage, condition severity and condition duration (rounds), all flat. A technique-scoped target never reaches a maneuver. Matching uses the technique as authored, not the caster's specialized variant.
_Avoid_: technique filter, technique modifier (the modifier is the source's; the scope is the target's), effect scope (a maneuver scope is `scope_maneuver_effect`)

**Technique effect context** (#4822):
The frozen `TechniqueEffectContext` that `technique_effect_context(sheet, technique, damage_type_id=None)` builds for one cast: the technique id, its gift and parent gift ids, its function set, the resonance ids its gift manifests as for the caster and the resolved damage type id. `technique_effect_total(sheet, context, targets)` sums the modifiers of the targets whose technique scopes all match it. Built once per cast, and the damage type slot is filled per damage profile.
_Avoid_: technique snapshot

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
- **menace** — the fear-facing sibling (named by ApostateCD 2026-07-23); feeds
  Intimidation checks via its check-scoped ``target_check_type`` (the #767/#512
  check-contribution seam carries character + equipment + fashion menace into the
  roll); seeded in ``world/seeds/social_checks.ensure_menace_target``. Clothing/
  cosmetics/distinctions grant it exactly like allure.
- **the five levers** (#4394): `income`, `reputation_gain` (+ `_society`, `_organization`),
  `relationship_gain`, `comfort`, `fatigue_cost`, each its own category with a target of the
  same name, read at one seam each through `world/mechanics/levers.py` (allowance and asset
  payout, regard writes, affection shifts, the residence comfort read, the fatigue charge).
  Percent levers are percentage points on a gain or a charge; comfort is whole levels.
  _Avoid_: a second reader for any of them, or scaling a loss (a sting, conflict).
- **disguise sight** (#4396): the `disguise_sight` category, one target per `DisguiseKind`
  value (`mundane`, `magical`); a positive total reveals a disguise of that kind to the
  character with no identification check. Read by the persona reveal rule through
  `forms.services.identification.pierced_disguise_kinds`. Not a percent.
  _Avoid_: true sight (a magic term), a second reader.
Bare/unknown `ModifierSource` rows contribute NOTHING to totals (#909) — grants must
ride a recognized source (distinction effect, achievement reward, comfort, equipment).
_Avoid_: inventing an "Allure" Trait/skill row; it is a modifier target.
