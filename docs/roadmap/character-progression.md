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
- **APIs:** Full viewsets/serializers for traits, skills, progression, classes (paths, character classes, aspects)
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
- Development point sources — all the ways dp are earned (scene participation, training, missions, combat, crafting, social, exploration). The primary source is a `perform_check` hook: every check that uses a trait flags that trait as "used this week." Weekly cron converts usage flags to development points and applies rust to unused skills. The hook MUST live on `perform_check`, not on downstream consumers (resolve_challenge, combat) so that social scene checks earn development too. See `docs/architecture/check-resolution-spectrum.md`
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
- XP rewards integration across all pillars (scenes, kudos, journals, GM rewards) — kudos→XP conversion done, see below for scene/GM notes
- Level caps for content participation (minimum/maximum level for joining activities)

### Magic XP Sinks (Spec A — done)
- **ThreadWeaving unlock acceptance spend** — `accept_thread_weaving_unlock` /
  `compute_thread_weaving_xp_cost` charge a Path-multiplied XP cost to open a new
  thread anchor kind for the character
- **XP-lock crossing** — `cross_thread_xp_lock` charges XP when a thread crosses an
  `ThreadXPLockedLevel` boundary, gating high-tier thread growth behind character XP
- Cross-reference: `docs/systems/magic.md` for the full model lineup

## Notes

### XP Rewards Integration Status

**Done:**
- Journal XP: Weekly awards for posts, praise, retorts (already wired)
- Kudos → XP: `claim_kudos_for_xp()` orchestrates atomic kudos claim + XP award
- First Impression XP: 3 XP to author, 5 XP to target on first relationship update
- Vote system: 7+1 weekly budget, toggle votes on interactions/journals/scene personas,
  weekly cron awards XP on diminishing returns curve (cap 50), Memorable Poses top 3 (3/2/1 XP)
- Random Scene bounties: 5 weekly targets (strangers + relationships), auto-validated claims
  (5+5 XP, first-time bonus +10), one reroll per week, weekly cron generation
- Scene completion → vote budget: participants get +1 bonus vote when a scene finishes

**Done (fatigue/effort system):**
- 12 stats in 4 categories: Physical (str/agi/sta), Social (cha/pre/com), Mental (int/wit/stb), Meta (lck/per/wil)
- Simplified CG stat allocation: budget = 2 * stat_count + bonuses, store 1-5 directly
- Three independent fatigue pools (physical/social/mental) with capacity from endurance stats + willpower
- Five fatigue zones (fresh/strained/tired/overexerted/exhausted) with threshold-based check penalties
- Five effort levels (very low/low/medium/high/extreme) with cost multiplier and check modifier
- Two-stage collapse mechanic via unified check system (endurance check → willpower power-through)
  - Medium collapses at exhausted only, high/extreme at overexerted+, very low/low never
- IC dawn fatigue reset cron (~8h real time) with scene deferral
- Rest command (10 AP, once per IC day, grants Well Rested +50% capacity)
- Action fatigue pipeline (execute_action_with_fatigue orchestrates full cycle)
- Vote budget scales by active character count (7 per character)
- Frontend: fatigue status display, effort selector with color gradient, rest button

**Fatigue — remaining work:**
- **"At home" location check for rest** — currently rest works anywhere; needs room/residence system
- **Social action conditions** — map each contested action (intimidate, seduce, persuade, etc.) to
  its applied condition on success, with target consent and kudos rewards
- **Aura farming / making an entrance / flourishing** — uncontested actions that affect resonance
  and use the fatigue pipeline, need action type definitions and resonance integration
- **Action type definitions** — define base fatigue costs per action, which pool each draws from,
  and wire into the scene action request system
- ~~**Development point hooks**~~ — DONE: dp awarded per check via action pipeline,
  threshold-based level-ups, WeeklySkillUsage accumulator, weekly rust + audit cron
- **Integration test for fatigue → check pipeline** — end-to-end test with real CheckRank/ResultChart
  fixture data (currently mocked)
- **Unified dice roll system** — fatigue checks use perform_check but the broader game needs a
  consistent roll resolution mechanic across all systems

**Done (GameWeek & unified weekly systems):**
- GameWeek/GameSeason models — formal week tracking, all weekly systems FK to GameWeek
- Unified weekly rollover cron — single orchestrator advances week then processes all systems
- All weekly models migrated: WeeklyVoteBudget, WeeklyVote, WeeklySkillUsage, RandomSceneTarget,
  WeeklyJournalXP, CharacterRelationship, DevelopmentTransaction
- Concurrent-safe: partial unique constraint on is_current, select_for_update in advance

**Not yet built (other progression):**
- **GM compensation:** Needs GMing system defined first
- **Training system:** Persistent TrainingAllocation with mentor bonuses
- **Path leveling requirements:** Scaling prerequisites engine


### Future Design: Aspect Focus as Path Evolution Guide

**Idea to explore:** Let players choose an aspect to "lean into" on their current path, creating both a mechanical bonus (stronger weight in that aspect for checks) and a narrative breadcrumb toward compatible higher-stage paths.

**Context:** Aspects (formerly called "spheres" in brainstorming) are broad archetypes (Warfare, Subterfuge, Diplomacy, etc.) that bridge paths and checks via `PathAspect` and `CheckTypeAspect` weights. Currently aspects are staff-configured on paths and invisible to players beyond display. The check bonus formula is `check_aspect_weight * path_aspect_weight * character_level`.

**Design questions to resolve:**
- When does the player choose their aspect focus? At path selection in CG, or after a few steps/levels?
- Does the chosen aspect focus increase that aspect's weight for checks, or is it purely a signal for path evolution eligibility?
- Could the focus narrow the set of available evolution paths (e.g., leaning into "Warfare" on Path of Steel opens Vanguard/Warlord but not Daredevil)?
- How does this interact with Audere Majora breakthrough moments — is the aspect focus part of the narrative threshold?
- Should players be able to shift their focus over time, or is it a commitment?
