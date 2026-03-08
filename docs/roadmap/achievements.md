# Achievements & Discoveries

**Status:** in-progress
**Depends on:** All systems (achievements track actions across every domain)

## Overview
A meta-engagement layer inspired by Everquest 2's discovery system and Steam achievements. Characters earn achievements for milestones across every system, with first-to-achieve "discoveries" that make early accomplishments feel special. Achievements are hidden by default and designed to surprise and delight — players discover them through play, not by browsing a checklist.

## Key Design Points
- **Hidden achievements:** Most achievements are hidden until earned, creating surprise and delight when triggered
- **Discovery system:** First-to-achieve tracking with IC/OOC timestamps. Supports simultaneous co-discoverers (e.g., a party all earning an achievement together). "Discovered by Alice, Bob, and Charlie"
- **Notification levels:** Per-achievement control — personal (only the earner sees), room (announced to current room), or gamewide (server-wide announcement). Sneaky achievements stay private
- **Stat tracking:** General-purpose counter system recording measurable actions across all systems. String-keyed for decoupled integration
- **Achievement chains:** Tiered achievements (kill 10/25/100/1000) connected via prerequisite FKs
- **Mechanical rewards:** Titles, bonuses, cosmetics awarded on achievement
- **Hand-crafted:** All achievements are staff-defined. Tooling can help batch-generate tiered achievements
- **Cross-cutting integration:** Every game system calls a simple service function to record stats and trigger achievement checks

## What Exists
- **Models:** StatTracker (per-character counters), Achievement (SharedMemoryModel definitions), AchievementRequirement (stat threshold conditions), Discovery (first-to-achieve with co-discoverer support), CharacterAchievement (earned records), AchievementReward (titles/bonuses/cosmetics)
- **Services:** increment_stat (atomic increment + achievement check), grant_achievement (with discovery tracking and batch support), get_stat
- **APIs:** AchievementViewSet (shows visible + earned hidden), CharacterAchievementViewSet (with filtering)
- **Admin:** Full admin with inlines for requirements and rewards
- **Tests:** Model tests, service tests (including prerequisite chains, discovery, batch grants), view tests
- **Progression integration:** AchievementRequirement in progression app now uses FK to achievements.Achievement

## What's Needed for MVP
- Relationship achievement definitions (first relationship, enemies-to-lovers, etc.)
- Combat achievement definitions and stat tracking hooks (depends on combat system)
- Crafting achievement definitions (depends on crafting system)
- Mission achievement definitions (depends on missions system)
- Achievement notification delivery system (personal/room/gamewide popups)
- Achievement browser UI — viewing earned achievements, discovery hall of fame
- Achievement page sharing — letting players show their achievements to friends
- Path progression integration — linking achievements as Path step requirements

## Notes

See `docs/plans/2026-03-08-relationships-achievements-design.md` for the full design document.
