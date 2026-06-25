# Progression glossary

> Durance, XP, Kudos, and Development Points are cross-cutting terms — see the root `AGENT_GLOSSARY_MAP.md`.

**Unlock**:
An authored advancement target a character can spend XP to acquire — e.g. `ClassLevelUnlock` (a class level) or `TraitRatingUnlock` (a major trait threshold) — whose availability is governed by Requirements.
_Avoid_: perk, purchase, upgrade.

**Requirement**:
An authored gate attached to an Unlock, evaluated per character through `is_met_by_character(character) -> (bool, str)`. Concrete kinds include Trait, Level, ClassLevel, MultiClass, Tier, Achievement, Relationship, and Legend requirements.
_Avoid_: prerequisite, condition (reserve "condition" for the conditions system).

**ClassLevelAdvancement**:
The receipt for a single within-tier class-level advance performed through the Ritual of the Durance; it records level_before/after, officiant, ritual, and scene, and survives character death. Its tier-crossing sibling is `AudereMajoraCrossing`, both sharing `AbstractClassLevelAdvancement`.
_Avoid_: level-up event, training record.

**PathIntent**:
A character's mutable declared intention for their next Path — one row per sheet, overwritten on re-declaration — which the Audere Majora offer pre-selects when it is among the eligible paths.
_Avoid_: path receipt, path choice (it is an aspiration, not a committed record).
