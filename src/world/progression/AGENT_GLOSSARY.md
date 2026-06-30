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

**trainer-of-record**:
The `CharacterSheet` stored on a `DuranceTrainingSite` as the room's designated officiant.
The actual eligibility gate (`assert_can_officiate`) runs on this trainer, not on any
live-present character, so an inductee can self-conduct their Durance at the site.
_Avoid_: static officiant, pre-assigned trainer.

**training site**:
A room registered as a place where the Ritual of the Durance can be conducted without a
live higher-level PC, by binding a trainer-of-record to the room (`DuranceTrainingSite`).
The rite still runs through the full ritual session lifecycle — only the officiant source
differs between a site-convened session and a live-officiant ceremony.
_Avoid_: self-serve durance, training room.
