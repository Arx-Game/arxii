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

**Approach**:
A way to resolve a challenge (`ChallengeApproach`), connecting what a character can do (an `Application`) with how it is rolled (a `CheckType`) for a specific challenge template, optionally gated by a required effect property.
_Avoid_: method, tactic, option, resolution path

**SituationTrapLink**:
An authored trap blueprint carried by a `SituationTemplate` — name, consequence
pool, detect/disarm check types and difficulties, hidden/obvious default.
Materialized into a real `room_features.Trap` row by `instantiate_situation`;
carries no runtime state (no armed/detected/position — those are fresh per
instantiated Trap).
_Avoid_: trap template, trap blueprint (as a class name), situation trap
