# World Clock & Scheduled Systems

**Status:** not-started
**Depends on:** Server infrastructure (Evennia scripts/Twisted services)
**Depended on by:** Action Points, Relationships, Magic, Codex, Missions, Crafting, Scenes, Stories

## Overview
The central time engine that drives the living world. Everything from AP regeneration to weather changes to holiday festivals depends on a reliable game clock and scheduler. Multiple systems already have time-dependent logic implemented but nothing actually triggers it — there's no heartbeat. This domain covers the IC game clock, the real-time scheduler that calls periodic tasks, and the world-atmosphere systems (weather, timed emits, seasons) that make the grid feel alive.

## Key Design Points

### Game Clock
- **3:1 time ratio:** Three IC days pass per one real day (established in stories-gm.md). This means ~1 IC year per ~4 real months
- **IC calendar:** The game world needs its own calendar with named months, days, seasons. Whether it mirrors real-world structure (12 months, 4 seasons) or is custom is a design choice
- **Character aging:** Characters age at the 3:1 ratio. Birthdays are trackable events
- **Day/night cycle:** At 3:1, each IC day is ~8 real hours. Rooms and the grid can reflect time of day
- **Canon time vs scene time:** Canon time advances continuously. Scene time is narrative (10 IC minutes can span hours of real typing). These coexist — the stories-gm.md time reconciliation design applies here

### Scheduler Infrastructure
- **Periodic task runner:** Something needs to call `apply_daily_regen()`, reset weekly counters, expire temporary effects, and run research rolls. Options: Evennia Scripts (built-in, Twisted-based), Celery Beat (industry standard, heavier), or a lightweight approach using Django management commands + OS-level cron
- **Task categories by frequency:**
  - **Per IC day (~8 real hours):** AP daily regen, anima fade for out-of-combat techniques, day/night cycle update, weather changes
  - **Per real day:** Relationship temporary point decay cleanup, character aging tick
  - **Per real week:** Relationship development limit reset (week_reset_at), skill rust checks, weekly AP regen
  - **Hourly:** Research project roll ticks (codex), timed room emits cycling
  - **Event-driven (not periodic):** Season changes, holidays, staff-triggered world events
- **Idempotency:** Every periodic task must be safe to run twice — use timestamps (last_daily_regen, week_reset_at) to prevent double-application if the scheduler fires late or catches up after downtime
- **Catch-up logic:** If the server was down for 3 days, should AP regen accumulate for missed days? Probably yes with a cap. Design per-system

### Weather System
- **Weather per area:** Different regions can have different weather. A coastal city has storms; a desert has sandstorms; underground areas have no weather
- **Weather affects gameplay:** Travel speed, combat modifiers, crafting availability, mission availability. Weather should be mechanically meaningful, not just flavor
- **Weather progression:** Weather changes over time following patterns (clear → cloudy → rain → storm → clearing). Not purely random — weighted transitions
- **Seasonal influence:** Season shifts weather probability tables. Winter means more snow, summer means more heat. Tied to the IC calendar
- **Staff override:** Staff can force weather for story purposes (a supernatural storm during a boss fight)

### Timed Emits & Ambient Atmosphere
- **Room emits:** Periodic ambient messages that make rooms feel alive. A tavern emits chatter and clinking glasses; a forest emits birdsong and rustling leaves. These cycle through a pool of messages
- **Time-of-day emits:** Different emits for dawn, day, dusk, night. A market square is bustling at noon and quiet at midnight
- **Weather-reactive emits:** Rain patters on windows, wind howls through corridors. Emits change based on current weather
- **Event emits:** Staff-configured one-time or recurring broadcasts. Town crier announcements, festival fanfare, war drums in the distance
- **Emit frequency:** Configurable per room/area. High-traffic social hubs emit more often; wilderness emits less

### Holidays & Seasonal Events
- **IC calendar events:** Named festivals, holy days, market days tied to IC dates. These recur yearly on the IC calendar
- **Mechanical effects:** Holidays can grant bonuses (XP multipliers, special shop inventory, unique missions available only during the festival)
- **World state changes:** Decorations appear in rooms, NPCs change behavior, special locations open
- **Birthday tracking:** Characters have IC birthdays derived from their creation date mapped to the IC calendar. Birthday achievements, social recognition

### Rate Limiting & Cooldowns
- **Weekly limits:** Relationship developments (7/week), potentially skill training sessions, crafting attempts. All need reliable week boundaries and reset logic
- **Daily limits:** AP regen, mission attempts, research rolls. Need reliable day boundaries
- **Cooldowns:** Per-action cooldowns (e.g., can't use a powerful ability again for N IC hours). Need a general-purpose cooldown tracker
- **Display to players:** Players need to see "3 of 7 developments used this week" and "resets in 2 days 4 hours." The clock must be queryable from the frontend

## What Exists
- **Action Points:** `apply_daily_regen()` and `apply_weekly_regen()` methods fully implemented and tested, with `last_daily_regen` timestamp. No scheduler calls them
- **Relationships:** `week_reset_at` field on CharacterRelationship, `developments_this_week` / `changes_this_week` counters with reset logic in `create_development()`. Temporary point decay calculated on read via `current_temporary_value()`
- **Forms:** `TemporaryFormChange` with `duration_type` (REAL_TIME, GAME_TIME, SCENE, UNTIL_REMOVED) and `expires_at`
- **Conditions:** `expires_at`, `rounds_remaining`, `suppressed_until` fields — combat-round-based timing
- **Evennia Scripts:** Custom `Script` typeclass exists in `src/typeclasses/scripts.py` with interval/repeat support. Not used by any game system
- **Server hooks:** `at_server_startstop.py` has empty stubs for startup/shutdown/reload hooks
- **Twisted service plugins:** Empty stubs available for registering background services
- **Stories design:** 3:1 time ratio and three time modes (canon, scene, session) documented but not implemented

## What's Needed for MVP

### Infrastructure (build first — everything else depends on this)
- Game clock model — current IC date/time, time ratio config, IC calendar definition
- Scheduler choice and setup — Evennia Scripts, Celery, or management commands + OS cron
- Central tick dispatcher — calls registered periodic tasks at appropriate intervals
- Frontend time display — current IC date/time, day/night indicator, queryable for cooldown countdowns

### Periodic Task Wiring (connect existing logic to the scheduler)
- AP daily/weekly regen cron job
- Relationship weekly limit reset cron job
- Relationship temporary point decay cleanup
- Anima fade for out-of-combat techniques (hourly)
- Form expiration cleanup (real-time and game-time durations)
- Condition expiration cleanup (time-based, not round-based)
- Research project tick (codex — hourly or per-IC-day skill rolls)
- Skill rust tick (weekly — skills decay without use)

### Atmosphere (makes the world feel alive)
- Weather model — current weather per area, transition rules, seasonal weights
- Weather change cron — periodic weather transitions
- Room emit system — ambient message pools with time-of-day and weather variants
- Emit cycling cron — periodic emit delivery to occupied rooms

### Calendar & Events
- IC calendar with named months/seasons
- Holiday/festival definitions tied to IC dates
- Birthday tracking for characters
- Event emit system — staff-configured broadcasts (one-time and recurring)
- Seasonal effect integration — weather tables, available missions, shop inventory

### Rate Limit Display
- API endpoint for "time until weekly reset" / "daily uses remaining"
- Frontend widget showing cooldown timers and usage counts

## Design Questions
- **Evennia Scripts vs Celery vs OS cron?** Scripts are built-in and Twisted-native but less battle-tested for complex scheduling. Celery is robust but adds Redis/RabbitMQ dependency. OS cron + management commands is simplest but least flexible. The right choice depends on how many concurrent periodic tasks we expect
- **Custom IC calendar or mapped real-world calendar?** A custom calendar (with lore-appropriate month/season names) is more immersive but adds complexity. Mapping to real-world months with IC names is simpler
- **Weather granularity?** Per-room, per-area, or per-region? Per-area (the 9-level spatial hierarchy) seems right — weather at the District or Neighborhood level
- **Emit spam prevention?** How often is too often? Should emits suppress when players are actively RPing in a scene?

## Notes

Multiple systems already have the per-item logic built (AP regen, relationship decay, form expiration) — the missing piece is the scheduler that ties them together. This is infrastructure work that unblocks gameplay across many domains.
