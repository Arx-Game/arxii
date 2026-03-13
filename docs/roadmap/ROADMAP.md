# Arx II Roadmap

> For AI agents and developers: this is the big-picture view of what needs to be built
> for Arx II to reach MVP and start alpha playtesting. Each domain links to a stub file
> with more detail. Check those stubs before starting work on any system.

---

## What Is Arx II?

Arx II is a **web-first multiplayer RPG** — an MMO designed for collaborative roleplay at
a scale no tabletop game or traditional MUSH can achieve. Hundreds of adventuring parties
share one persistent world where every player's actions affect everyone else. The React
frontend is the primary interface; telnet is a secondary compatibility goal.

The game has three interconnected gameplay pillars. Most systems span all three — these are
loose conceptual groupings, not rigid boundaries.

### The Three Pillars

1. **Living Grid** — Characters roam the world solo or in small groups, taking missions,
   interacting with rooms and objects, and changing the world through their actions. A
   character might assassinate a target for their guild, protect a caravan, go harvesting,
   or fight in a war — and the consequences ripple outward.

2. **Character Relationships** — Players RP together, develop relationships, grow emotionally,
   strengthen bonds that improve combat effectiveness, share secrets, and discover magic through
   their connections. This is the heart of the game — MUSH players already love relationship RP,
   and our systems mechanically reward it.

3. **GM Tables** — Staff and volunteer GMs run stories for players. Each GM manages a "table"
   of PCs, overseeing their story arcs and adventures. GMs level up with trust, gaining the
   ability to run higher-impact stories. One staffer coordinates all GMs to maintain a single
   connected world.

## Design Principles

These are **hard requirements**, not aspirations. If a system doesn't meet these, it ships
broken regardless of technical correctness.

- **Engagement is survival.** The game lives or dies on social energy. If players aren't having
  fun and falling in love with their characters and the world, the self-sustaining RP ecosystem
  collapses. Systems must actively create fun, not just be mechanically correct.

- **Reward what players already enjoy.** RP, relationships, creative writing, dramatic moments —
  these are what MUSH players do naturally. Our systems give mechanical rewards for them.

- **Escape valves everywhere.** Encourage dramatic intensity and rivalry, but always provide easy
  de-escalation and opt-out. Players must never feel trapped or obligated. When drama stops being
  fun, there must be an easy exit.

- **No PVP killing.** This frees us from symmetrical balance concerns and lets us optimize for
  "feels cool" rather than "perfectly fair." Combat is always Players vs. the Bad Guys.

- **Heroic by design.** Systems should consistently set the stage for breakthrough moments — being
  battered down, on the edge of defeat, then breaking through to become who you were meant to be.
  Think superhero team-up arcs, not grindy attrition.

- **Web-first UX.** Design for modern web interfaces with interactive components, visual feedback,
  and responsive layouts. Don't design around text-command-and-response patterns. Let telnet
  support follow where it can.

## System Domains

| Domain | Status | Summary |
|--------|--------|---------|
| [Character Creation & Identity](character-creation.md) | skeleton | 11-stage CG flow, backstory, appearance, species, paths |
| [Character Progression & XP](character-progression.md) | in-progress | XP, skills, path steps, Audere Majora, power tiers, the Durance |
| [Magic System](magic.md) | in-progress | Affinities, resonances, gifts, techniques, threads, spells |
| [Combat](combat.md) | not-started | Party combat, battle scenes, duels |
| [Missions & Living Grid](missions.md) | not-started | Branching narrative quests, world consequences, CK-style events |
| [Crafting, Fashion & Economy](crafting-economy.md) | not-started | Crafting, fashion-resonance loop, housing, shops, domains, ships |
| [Items & Equipment](items-equipment.md) | not-started | Worn items, body slots, item stats, fashion integration |
| [Relationships & Bonds](relationships.md) | in-progress | Relationship types, situational mods, soul tethers, party bonds |
| [RP Interaction & Scenes](rp-scenes.md) | in-progress | Rich text editor, action-attached poses, scene engagement |
| [Stories & GM Tables](stories-gm.md) | in-progress | Story arcs, GM tables, trust tiers, time reconciliation |
| [Codex & Knowledge](codex.md) | in-progress | Lore repository, character-scoped knowledge, research, secrets |
| [Journals & Expression](journals.md) | in-progress | IC writing, praises/retorts, freeform tags, weekly XP rewards |
| [Societies & Organizations](societies.md) | in-progress | Societies, organizations, reputation, legend, alter egos |
| [Achievements & Discoveries](achievements.md) | in-progress | Achievement tracking, first-to-discover, stat tracking, chains |
| [OOC Social & Community](ooc-social.md) | in-progress | Kudos, friend tracking, visibility controls, engagement tools |
| [World Clock & Scheduled Systems](world-clock.md) | in-progress | Game clock, scheduler, weather, timed emits, holidays, rate limit resets |
| [Tooling](tooling.md) | in-progress | Player building tools, GM tools (level-gated), staff tools |

### Recent Infrastructure Changes

- **ModifierTarget rename (Phase 1 complete):** `ModifierType` has been renamed to `ModifierTarget`
  across the entire codebase for clarity. Stat-category targets now have a `target_trait` FK for
  type-safe lookups. Remaining categories (action_points, development, etc.) will get target FKs
  when their respective systems are built. See `src/world/mechanics/TECH_DEBT.md` for the tracking
  table.

### Status Key

- **skeleton** — Core structure and models exist, but major features are still missing
- **in-progress** — Some pieces are built, significant work ahead
- **not-started** — Nothing meaningful built yet
