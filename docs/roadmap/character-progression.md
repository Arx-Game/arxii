# Character Progression & XP

**Status:** in-progress
**Depends on:** Traits, Skills, Magic, Paths, Relationships, Missions

## Overview
The central spine connecting every system in the game. Characters develop through XP (earned via RP activities), skill development (through use and training), and Path steps (leveling their magical calling). Progression touches all three gameplay pillars and is the primary long-term motivation loop.

## Key Design Points
- **XP economy:** Earned through RP activities across all pillars — scene participation, kudos from other players, GM rewards, journal writing, GMing (for the GM's own character)
- **Skills:** Develop through use, with XP spent at threshold unlocks (10, 20, 30, 40, 50). Development points accumulate through skill use on missions, in training scenes, and during GM adventures
- **Path steps:** Levels on a character's magical calling. Requirements get harder as you climb — need legend, XP, skills, magical affinity. Paths progress through tiers: Prospect, Potential (3-5), Puissant (6-10), and beyond
- **Audere Majora / Crossing the Threshold:** Dramatic breakthrough moments at steps after multiples of 5 (6, 11, 16, 21). The true power tier gates — characters must have a narrative breakthrough to advance
- **Spells:** Independent of Path — even quiescent (non-magical) characters can use hedge magic. In the hands of the truly powerful, spells are devastating
- **Path discovery:** Characters can research and unlock new Paths, eventually switching their calling
- **The Durance:** Each character's overarching story of magical discovery and who they truly are

## What Exists
- **Models:** Trait, CharacterTraitValue, PointConversionRange, CheckRank, ResultChart (traits). Skill, Specialization, CharacterSkillValue with development/rust tracking (skills). Path with evolution hierarchy through 6 tiers, Aspect, PathAspect (classes). XP and kudos models in progression app
- **Legend system:** LegendEntry, LegendSpread, LegendEvent (group deeds), LegendSourceType, LegendDeedStory (player narratives), SpreadingConfig. Materialized views for fast character/guise legend totals. Service functions for deed creation, spreading with cap enforcement. LegendRequirement for path leveling
- **Unlock system:** XPCostChart, ClassLevelUnlock, requirement types (Trait, Level, ClassLevel, MultiClass, Achievement, Relationship, Legend, Tier), CharacterUnlock, spend_xp_on_unlock service
- **APIs:** Full viewsets/serializers for traits, skills, progression
- **Frontend:** XP/Kudos page in progression section
- **Tests:** Extensive tests for traits, skills, kudos, character XP, path history, legend

## What's Needed for MVP

### Legend (remaining)
- Legend spreading check formula — exact social check mechanics and audience factor calculations (tuning, depends on check system integration)
- Legend UI — viewing legendary deeds, writing deed stories, spreading interface
- Item legend — items carrying legend that transfers to possessors (depends on items system)
- Organization legend sharing — org deeds shared to members by rank
- Achievement stat hooks — firing legend.deeds_earned, legend.personal_total, legend.times_spread etc.
- Legend achievement definitions (Noteworthy, Legendary, Mythic, Bard's Favorite, etc.)

### Skill Development
- Post-CG skill advancement mechanics — development point scaling (100 dp from 10→11, 200 from 11→12, etc.), XP thresholds at every 10 (10, 20, 30, 40, 50)
- Skill rust mechanics — debt accumulation (character_level + 5 per week, capped at current level's dev cost), must pay off before forward progress
- Development point sources — all the ways dp are earned (scene participation, training, missions, combat, crafting, social, exploration)
- **Training system** — persistent TrainingAllocation model (skill + optional mentor guise + AP amount). Formula: `base_gain = 5 × AP × path_level`, `mentor_bonus = (AP + teaching) × (mentor_total / student_total) × (relationship_tier + 1)`. Overflow carries over across levels. See `docs/plans/2026-03-10-training-system-design.md`
- **TODO: Relationship tier calculation** — training mentor bonus uses relationship tier (currently stubbed at 0). Need to define tier breakpoints from affection/impression values
- Weekly cron processes training + rust (depends on world clock)
- Scene check dev points — certain scene checks award dp and prevent rust (defined in scenes roadmap)

### Path Leveling
- Path step requirements engine — scaling requirements from trivial (level 2: 100 XP, 30 in primary skill, 10 legend, find a trainer, some gold) to nearly impossible (level 21: Audere Majora 4th crossing, extreme achievements, god-tier trainer quest)
- Audere Majora system — the dramatic threshold-crossing mechanic that gates major power tiers
- Trainer system — finding trainers, training costs, trainer tiers
- Path switching/discovery mechanics

### Other
- Spell system (distinct from techniques — learnable magic independent of Path)
- XP rewards integration across all pillars (scenes, kudos, journals, GM rewards)
- Level caps for content participation (minimum/maximum level for joining activities)

## Notes

### Future Design: Aspect Focus as Path Evolution Guide

**Idea to explore:** Let players choose an aspect to "lean into" on their current path, creating both a mechanical bonus (stronger weight in that aspect for checks) and a narrative breadcrumb toward compatible higher-stage paths.

**Context:** Aspects (formerly called "spheres" in brainstorming) are broad archetypes (Warfare, Subterfuge, Diplomacy, etc.) that bridge paths and checks via `PathAspect` and `CheckTypeAspect` weights. Currently aspects are staff-configured on paths and invisible to players beyond display. The check bonus formula is `check_aspect_weight * path_aspect_weight * character_level`.

**Design questions to resolve:**
- When does the player choose their aspect focus? At path selection in CG, or after a few steps/levels?
- Does the chosen aspect focus increase that aspect's weight for checks, or is it purely a signal for path evolution eligibility?
- Could the focus narrow the set of available evolution paths (e.g., leaning into "Warfare" on Path of Steel opens Vanguard/Warlord but not Daredevil)?
- How does this interact with Audere Majora breakthrough moments — is the aspect focus part of the narrative threshold?
- Should players be able to shift their focus over time, or is it a commitment?
