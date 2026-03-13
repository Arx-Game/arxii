# Game Clock App

Central time engine for Arx II. Tracks IC time, provides day/night and seasonal awareness, and dispatches periodic game tasks via a scheduler.

## Models

### GameClock (singleton)
Anchor-based IC time derivation. IC time = `anchor_ic_time + (now - anchor_real_time) * time_ratio`.
- `anchor_real_time`, `anchor_ic_time` — the anchor pair
- `time_ratio` — IC seconds per real second (default 3.0)
- `paused` — emergency stop

### GameClockHistory
Audit log for clock adjustments. Stores old/new anchor values, who changed it, and why.

### ScheduledTaskRecord
Per-task tracking of last run time. Tasks are auto-created on first scheduler tick.
- `task_key` — unique string identifier
- `last_run_at` — real time of last execution
- `enabled` — staff can disable individual tasks via admin

## Service Functions

### Clock Queries
- `get_ic_now()` — current IC datetime
- `get_ic_phase()` — TimePhase enum (DAWN, DAY, DUSK, NIGHT) with season-adjusted boundaries
- `get_ic_season()` — Season enum from IC month
- `get_light_level()` — float 0.0-1.0 for atmospheric lighting
- `get_ic_date_for_real_time(real_dt)` — convert real to IC datetime
- `get_real_time_for_ic_date(ic_dt)` — convert IC to real datetime

### Clock Management (staff)
- `set_clock()` — set IC time (creates clock or re-anchors)
- `set_time_ratio()` — change ratio with re-anchor
- `pause_clock()` / `unpause_clock()` — emergency pause

## Scheduler

### GameTickScript (Evennia Script)
Persistent script that ticks every 5 minutes, calling `run_due_tasks()`.
Created automatically in `at_server_start()`.

### Task Registry
Tasks registered in `tasks.py` via `register_all_tasks()`, called at server startup.

### Wired Tasks
| Task | Frequency | Source App |
|------|-----------|------------|
| AP daily regen | 24h real | action_points |
| AP weekly regen | 7d real | action_points |
| Journal weekly reset | daily sweep | journals |
| Relationship weekly reset | daily sweep | relationships |
| Form expiration cleanup | hourly | forms |
| Condition expiration cleanup | hourly | conditions |

## API Endpoints

- `GET /api/clock/` — current IC time, phase, season, light level
- `GET /api/clock/convert/` — date conversion (IC<>real)
- `POST /api/clock/adjust/` — set IC time (staff only)
- `POST /api/clock/ratio/` — change time ratio (staff only)
- `POST /api/clock/pause/` — pause clock (staff only)
- `POST /api/clock/unpause/` — unpause clock (staff only)

## Three Time Contexts

1. **World clock (IC)** — canonical game time at 3:1 ratio. Day/night, seasons, atmospheric.
2. **Scene time** — RP events freeze IC time for participants. Scene system owns this.
3. **Real time** — progression gating (weekly XP, AP regen, relationship limits).

## Integration Points

- **Any IC time query** — `get_ic_now()`
- **Day/night mechanics** — `get_ic_phase()` or `get_light_level()`
- **Seasonal mechanics** — `get_ic_season()`
- **Event scheduling** — `get_real_time_for_ic_date()`
- **IC timestamps on models** — stamp `get_ic_now()` at creation, store as concrete value
