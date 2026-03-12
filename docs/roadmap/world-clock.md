# World Clock & Scheduled Systems

**Status:** in-progress
**Depends on:** Server infrastructure (Evennia scripts/Twisted services)
**Depended on by:** Action Points, Relationships, Magic, Codex, Missions, Crafting, Scenes, Stories, Journals, Forms, Conditions

## Overview
The central time engine that drives the living world. An anchor-based game clock derives IC time from real time at a configurable ratio (default 3:1). A persistent Evennia Script dispatches registered periodic tasks. Service functions provide the query layer for all downstream systems.

## Three Time Contexts

1. **World clock (IC time)** — canonical game world time at 3:1 ratio. Drives day/night, seasons, atmospheric mechanics. Applies to characters on the grid not in a scene.
2. **Scene time** — RP events capture an IC moment; mechanics check scene time for participants. Scene system owns this, not the clock.
3. **Real time** — progression fairness gating (weekly XP caps, AP regen, relationship limits). More intuitive for players than IC-derived intervals.

## Key Design Points
- **Anchor-based derivation:** IC time = `anchor_ic_time + (now - anchor_real_time) * time_ratio`. Never a ticking counter.
- **Staff adjustment:** Set a new anchor for time skips or nudges. History model logs all changes.
- **Idempotent tasks:** Every periodic task is safe to run twice via per-system timestamps.
- **Scheduler-agnostic tasks:** Task logic lives in app service functions. Scheduler only calls them — swappable from Evennia Scripts to Celery later.
- **Historical IC timestamps:** Stored as concrete values on models (journals, scenes, events). Unaffected by anchor changes.
- **Season-adjusted phases:** Day/night boundaries shift by season (longer summer days, longer winter nights).
- **Calendar:** 12 months, 4 seasons, mapped real-world structure. Numbered months now, lore names added via config later.

## What Exists
- **AP regen methods:** `apply_daily_regen()`, `apply_weekly_regen()` fully implemented and tested. No scheduler calls them.
- **Journal weekly reset:** `WeeklyJournalXP.needs_reset()` / `reset_week()` with timestamp-based logic. Currently inline on access.
- **Relationship weekly reset:** `week_reset_at`, `developments_this_week` / `changes_this_week` counters with reset logic.
- **Form expiration:** `TemporaryFormChange` with `expires_at` for real-time duration. `GAME_TIME` duration type placeholder exists.
- **Condition expiration:** `ActiveCondition` with `expires_at`, `suppressed_until` fields. Indexed for efficient queries.
- **Relationship decay:** `current_temporary_value()` calculated on read via linear decay. No cleanup needed.
- **Evennia Scripts typeclass:** Custom Script class exists in typeclasses, supports interval/repeat/persistent. Unused.
- **Server hooks:** `at_server_startstop.py` has empty stubs for startup/shutdown/reload.
- **Stories design:** 3:1 time ratio and three time modes documented.

## What's Needed for MVP

### Clock Infrastructure ✅
- GameClock single-row model (anchor-based IC time derivation)
- GameClockHistory audit log
- Service functions: `get_ic_now()`, `get_ic_phase()`, `get_ic_season()`, `get_light_level()`, date conversion utilities
- Staff clock management: `set_clock()`, `set_time_ratio()`, `pause_clock()`, `unpause_clock()`
- Season-adjusted phase boundaries (dawn/day/dusk/night)
- REST API: public clock query, staff adjustment, date conversion
- GameTickScript (persistent Evennia Script scheduler)
- ScheduledTaskRecord model for task tracking
- Task registry with real-time and IC-time frequency support

### Periodic Task Wiring ✅
- AP daily/weekly regen batch job
- Journal weekly reset batch sweep
- Relationship weekly reset batch sweep
- Form expiration cleanup (real-time)
- Condition expiration cleanup (time-based)

### Deferred (future PRs)
- Weather system (own design + PR, consumes clock for season/time-of-day)
- Celestial atmosphere — moon phases, astrological conjunctions (part of atmosphere PR)
- IC calendar lore names (brainstorm separately, populate via config table)
- Aging mechanics — multiple age types (chronological, physical, unknown origin) need own design
- Birthday notifications and friend alerts (notification system consumes clock queries)
- `ic_birthdate` field on CharacterSheet
- Scene time integration (scene system responsibility)
- Event scheduling logic (event system consumes clock conversion API)
- Frontend clock widget and day/night atmospheric styling
- Celery migration (if scale demands it)
- Game-time form expiry (`DurationType.GAME_TIME`)
- Research project rolls (codex system)
- Skill rust (progression system)
- Anima fade out of combat (magic system)

## Design Document

See `docs/plans/2026-03-11-world-clock-design.md` for full design.

## Notes

Multiple systems already have per-item periodic logic built (AP regen, relationship decay, form expiration) — the missing piece is the scheduler that ties them together. This is infrastructure work that unblocks gameplay across many domains.

Time skips (e.g., 20 years between story arcs) are handled by setting a new anchor. Progression systems are unaffected (real-time gated). Narrative consequences are handled by bespoke staff scripts, not automated.
