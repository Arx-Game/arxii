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
- **GameWeek model:** Formal game week tracking with `GameWeek` and `GameSeason` models. All weekly systems FK to `GameWeek` instead of storing raw dates. Unified `weekly_rollover` cron orchestrator advances the week then runs all weekly processors in sequence.
- **AP regen:** `apply_daily_regen()`, `apply_weekly_regen()` batch jobs wired to scheduler.
- **Journal weekly reset:** `WeeklyJournalXP` uses `game_week` FK. `needs_reset()` / `reset_week()` compare FKs. Batch sweep resets all non-current-week trackers.
- **Relationship weekly reset:** `CharacterRelationship` uses `game_week` FK for `developments_this_week` / `changes_this_week` counters.
- **Vote processing:** `WeeklyVoteBudget`, `WeeklyVote` use `game_week` FK. Processed during weekly rollover.
- **Skill development:** `WeeklySkillUsage` uses `game_week` FK. Check-based DP accumulation + weekly rust processing.
- **Random scenes:** `RandomSceneTarget` uses `game_week` FK. Generated during weekly rollover.
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
- ~~Moon phases~~ — **built (#2845, ADR-0180)**: `MoonPhase` (8 phases) +
  `get_moon_phase()`/`get_moon_illumination()` as pure IC-time derivations (synodic
  cycle PLACEHOLDER 30 IC days, fixed epoch — no state, no cron writer; staff
  time-skips move the moon). Surfaced via the weather `Conditions` read + widget
  (night only). Astrological conjunctions remain deferred; the lycan consumer is
  **built (#2845, ADR-0183)**: `felt_moon_pull` (illumination × sky − shade) drives
  the `moon_control` window (`species.moon_reconcile` cron, 5-min DRAIN) — forced
  battle-form shift + shared Berserk on failure, Cani Moonlit Unease as flavor.
- **Consumer note (#2846, ADR-0179):** the sunlight bane/allergy system reads
  `get_ic_phase()` for its base-sun gate (full at DAY, reduced DAWN/DUSK, zero
  NIGHT) and registers the `species.sun_reconcile` cron (5-min, DRAIN band) —
  day/night is now a real mechanical pressure for sun-sensitive species, with
  clothing/shade/magic mitigation and an AFK auto-flee guard.
- IC calendar lore names (brainstorm separately, populate via config table)
- ~~Aging mechanics~~ — **built (#2756)**: three age axes on CharacterSheet
  (chronological derives from `ic_birth_year` vs `get_ic_now()`; biological =
  matured + withered years), deterministic Maturation Points, IC-cadence aging
  crons (`aging.birthday_tick` / `aging.decline_check` / `aging.death_sweep`),
  Frailty decline, dying window into the estates flow. See ADR-0172.
- ~~Birthday notifications~~ — **built (#2756)** as the Town Crier tidings
  digest (`FeedItemKind.BIRTHDAY`, merge-on-read), deliberately not push
  notifications; friends/watched filters remain a scale valve for later.
- ~~`ic_birthdate` field~~ — **built (#2756)** as `birthday_month`/`birthday_day`
  (celebrated date; Sleeper waking day) + nullable `ic_birth_year`.
- Scene time integration (scene system responsibility)
- Event scheduling logic (event system consumes clock conversion API)
- Frontend clock widget and day/night atmospheric styling
- Celery migration (if scale demands it)
- Game-time form expiry (`DurationType.GAME_TIME`)
- Research project rolls (codex system)
- Anima fade out of combat (magic system) — planned as part of `magic.md` Scope #6 (Soulfray Recovery & Decay)

## Design Document

See `docs/plans/2026-03-11-world-clock-design.md` for full design.

## Notes

Multiple systems already have per-item periodic logic built (AP regen, relationship decay, form expiration) — the missing piece is the scheduler that ties them together. This is infrastructure work that unblocks gameplay across many domains.

Time skips (e.g., 20 years between story arcs) are handled by setting a new anchor. Progression systems are unaffected (real-time gated). Narrative consequences are handled by bespoke staff scripts, not automated.
