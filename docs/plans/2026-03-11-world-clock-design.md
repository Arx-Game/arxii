# World Clock & Scheduler Design

**Goal:** Build the central time engine that tracks IC time, provides day/night and seasonal awareness, runs periodic game tasks, and exposes an API for frontend and downstream systems.

**Architecture:** A single-row anchor-based clock model derives IC time from real time via a configurable ratio (default 3:1). A persistent Evennia Script ticks on a fixed interval and dispatches registered periodic tasks. Service functions provide the query layer that all downstream systems consume.

---

## Core Concepts

### Three Time Contexts

1. **World clock (IC time)** — the canonical "what time is it in the game world." Advances at 3:1 ratio from a staff-configurable anchor. Drives day/night, seasons, atmospheric mechanics. Applies to characters on the grid not in a scene.
2. **Scene time** — a specific RP event captures an IC moment and stays there. Mechanics check the scene's IC time for participants, not the world clock. GMs can advance scene time within their session. Scene time ownership belongs to the scene system, not the clock.
3. **Real time** — progression fairness gating. Weekly XP caps, AP regen boundaries, relationship development limits. Uses real-time because it's more intuitive for players ("I haven't done anything on Arx today" vs "I haven't done anything in 8 hours").

### Time Skips

Staff can jump the clock forward (e.g., 20 years between story arcs) by setting a new anchor. Periodic/progression systems are unaffected — they use real-time gating and just resume from the new "now." Narrative consequences (aging, world changes) are handled by bespoke staff scripts on a case-by-case basis, not automated by the clock.

### Historical IC Timestamps

When a journal entry, scene, or event is created, its IC timestamp is stored as a concrete value in the database. These are historical facts that never change regardless of future anchor adjustments. The anchor math only governs "what time is it right now?"

---

## Models

### GameClock (single-row config)

| Field | Type | Description |
|-------|------|-------------|
| `anchor_real_time` | DateTimeField | Real-world datetime when clock was last set |
| `anchor_ic_time` | DateTimeField | IC datetime at the anchor point |
| `time_ratio` | FloatField (default 3.0) | IC seconds per real second |
| `paused` | BooleanField (default False) | Emergency/maintenance pause |

Current IC time derivation: `anchor_ic_time + (now - anchor_real_time) * time_ratio`

Staff adjustment (including time skips) sets a new anchor: "as of right now, IC time is X." In practice, the anchor is set once at game launch and rarely touched — small nudges to align IC holidays with OOC weekends, and rare large jumps between story arcs.

### GameClockHistory (audit log)

| Field | Type | Description |
|-------|------|-------------|
| `changed_by` | FK to AccountDB | Staff member who made the change |
| `changed_at` | DateTimeField (auto_now_add) | When the change was made |
| `old_anchor_real_time` | DateTimeField | Previous anchor real time |
| `old_anchor_ic_time` | DateTimeField | Previous anchor IC time |
| `old_time_ratio` | FloatField | Previous ratio |
| `new_anchor_real_time` | DateTimeField | New anchor real time |
| `new_anchor_ic_time` | DateTimeField | New anchor IC time |
| `new_time_ratio` | FloatField | New ratio |
| `reason` | TextField | Staff notes on why the change was made |

### ScheduledTaskRecord (task tracking)

| Field | Type | Description |
|-------|------|-------------|
| `task_key` | CharField (unique) | String identifier for the task |
| `last_run_at` | DateTimeField (nullable) | When this task last completed |
| `last_ic_run_at` | DateTimeField (nullable) | IC time of last run (for IC-frequency tasks) |
| `enabled` | BooleanField (default True) | Staff can disable individual tasks |

---

## Service Functions (`world.game_clock.services`)

### Clock Queries

- **`get_ic_now()`** — returns current IC datetime. Primary entry point for everything.
- **`get_ic_phase()`** — returns TimePhase enum (DAWN, DAY, DUSK, NIGHT) from IC hour with season-adjusted boundaries. Summer days are longer, winter nights are longer.
- **`get_ic_season()`** — returns Season enum (SPRING, SUMMER, AUTUMN, WINTER) from IC month.
- **`get_light_level()`** — returns float 0.0–1.0 for gradual transitions. Derived from IC hour + season. Useful for atmospheric descriptions and mechanics.
- **`get_ic_date_for_real_time(real_dt)`** — converts real datetime to IC datetime. For event scheduling ("when does the Feast of Shadows fall OOC?").
- **`get_real_time_for_ic_date(ic_dt)`** — reverse lookup. IC datetime to approximate real datetime.

### Clock Management (staff only)

- **`set_clock(*, new_ic_time, changed_by, reason)`** — sets new anchor, logs to history.
- **`set_time_ratio(*, ratio, changed_by, reason)`** — changes the ratio, logs to history.
- **`pause_clock(*, changed_by, reason)` / `unpause_clock()`** — emergency pause.

### Phase Boundaries (season-adjusted)

Dawn/day/dusk/night boundaries shift by season. Example defaults:

| Season | Dawn | Day | Dusk | Night |
|--------|------|-----|------|-------|
| Spring | 5:30 | 6:30 | 18:30 | 19:30 |
| Summer | 4:30 | 5:30 | 20:00 | 21:00 |
| Autumn | 6:00 | 7:00 | 17:30 | 18:30 |
| Winter | 7:00 | 8:00 | 16:30 | 17:30 |

These would be constants initially, movable to a config model if staff wants to tune them.

---

## IC Calendar

Mapped real-world structure: 12 months, ~30 days each, 4 seasons. Month names are numbered placeholders for now — lore names will be added later via a config table after a separate brainstorm.

Season mapping:
- Months 3–5: Spring
- Months 6–8: Summer
- Months 9–11: Autumn
- Months 12, 1–2: Winter

### Birthdays

Characters with an IC birthdate on their character sheet can be queried against `get_ic_now()` to determine upcoming birthdays. The clock provides the IC date; the birthday notification system is a downstream consumer (out of scope for this PR, but the query capability exists).

---

## Scheduler

### GameTickScript (Evennia Script)

A single persistent Evennia Script created in `at_server_start()` if it doesn't already exist. Runs on a fixed real-time interval (e.g., every 5 minutes). On each tick:

1. Calls `get_ic_now()` to know current IC time
2. Iterates registered tasks, checking `ScheduledTaskRecord.last_run_at` against each task's frequency
3. Executes due tasks (calling their service functions)
4. Updates `last_run_at` / `last_ic_run_at`

### Task Registration

A simple registry — a list of task definitions, each with:
- `task_key` — string identifier matching `ScheduledTaskRecord`
- `callable` — the batch service function to run
- `frequency` — timedelta for real-time tasks, or IC timedelta for IC-time tasks
- `frequency_type` — "real" or "ic"

### Design for Scheduler Replacement

The tasks themselves are just service functions in their respective apps. The scheduler only calls them. If Evennia Scripts are outgrown at scale, swapping to Celery Beat means changing only the scheduling mechanism — the task functions don't change.

### Idempotency

Every task is safe to run twice. Each system uses its own timestamps (`last_daily_regen`, `week_reset_at`) to prevent double-application. The scheduler's `last_run_at` is a scheduling optimization, not a correctness guarantee.

---

## Periodic Tasks to Wire

### Real-time gated (logic already exists)

| Task | App | Frequency | Notes |
|------|-----|-----------|-------|
| AP daily regen | action_points | 24 real hours | Calls `apply_daily_regen()` on all pools. Idempotent via `last_daily_regen`. |
| AP weekly regen | action_points | 7 real days | Calls `apply_weekly_regen()` on all pools. |
| Journal weekly reset | journals | Daily sweep | Batch resets stale `WeeklyJournalXP` trackers. Currently done inline on access; batch pre-cleans. |
| Relationship weekly reset | relationships | Daily sweep | Resets `developments_this_week` / `changes_this_week` counters. |

### Cleanup tasks (expiry sweeps)

| Task | App | Frequency | Notes |
|------|-----|-----------|-------|
| Form expiration | forms | Hourly | Deletes `TemporaryFormChange` where `duration_type=REAL_TIME` and `expires_at < now`. |
| Condition expiration | conditions | Hourly | Deactivates `ActiveCondition` where `expires_at < now`. |

### Future tasks (not wired in this PR)

| Task | App | Depends On |
|------|-----|------------|
| Weather transitions | atmosphere | Weather system |
| Moon phase / celestial updates | atmosphere | Atmosphere system |
| Research project rolls | codex | Research system |
| Skill rust | progression | Skill decay design |
| Game-time form expiry | forms | Clock integration with form system |
| Anima fade (out of combat) | magic | Combat/anima system |
| Birthday notifications | notifications | Notification system |

---

## API Endpoints

### Public

**`GET /api/clock/`** — current world time state
```json
{
    "ic_datetime": "0001-06-15T14:30:00",
    "year": 1,
    "month": 6,
    "day": 15,
    "hour": 14,
    "minute": 30,
    "phase": "day",
    "season": "summer",
    "light_level": 0.95
}
```

**`GET /api/clock/convert/`** — date conversion for event scheduling
- `?ic_date=0001-06-20` → returns approximate real datetime
- `?real_date=2026-04-15` → returns IC datetime

### Staff-only

**`PATCH /api/clock/`** — adjust the clock
```json
{
    "ic_datetime": "0021-01-01T00:00:00",
    "reason": "20-year time skip between Act I and Act II"
}
```

---

## Out of Scope (deferred to future PRs)

- **Weather system** — own design + PR, consumes clock for season/time-of-day
- **Celestial atmosphere** — moon phases, astrological conjunctions (part of weather/atmosphere PR)
- **IC calendar lore names** — brainstorm separately, populate via config table
- **Aging mechanics** — character sheet concern, consumes IC date. Multiple age types (chronological, physical, unknown origin) need own design
- **Birthday notifications** — downstream notification system consumes clock queries
- **`ic_birthdate` field on CharacterSheet** — could be this PR or deferred
- **Scene time integration** — scene system queries scene IC time, not world clock. Scene controls and abuse prevention are scene system concerns
- **Event scheduling logic** — event system consumes clock conversion API. Events can be scheduled within ~1 real week of when an IC date falls, with the event storing its own IC date
- **Frontend clock widget** — day/night atmospheric styling, clock display
- **Celery migration** — if scale demands it later, swap scheduler without changing tasks
- **Game-time form expiry** — `DurationType.GAME_TIME` needs clock + form system updates

---

## Integration Points

The clock system is consumed by many downstream systems. Key integration contracts:

- **Any system needing IC time** → call `get_ic_now()`
- **Day/night mechanics** (vampires, heists, law enforcement) → call `get_ic_phase()` or `get_light_level()`
- **Seasonal mechanics** (weather, magic, crops) → call `get_ic_season()`
- **Event scheduling** → call `get_real_time_for_ic_date()` / `get_ic_date_for_real_time()`
- **Scene system** → scenes store their own IC time; participants check scene time, not world clock
- **Atmospheric systems** (weather, moon, celestial) → consume clock, live in separate app
- **IC timestamps on models** → stamp `get_ic_now()` at creation time, store as concrete value
