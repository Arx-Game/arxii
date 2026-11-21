# Game Clock App

Central time engine for Arx II. Tracks IC time, provides day/night and seasonal awareness, and dispatches periodic game tasks via a scheduler.

## Models

### GameClock (singleton)
Anchor-based IC time derivation. IC time = `anchor_ic_time + (now - anchor_real_time) * time_ratio`.
- `anchor_real_time`, `anchor_ic_time` — the anchor pair
- `time_ratio` — IC seconds per real second (default 3.0)
- `paused` — emergency stop
- **Not seeded.** `GameClock.get_active()` returns `None` until staff create the row:
  Django admin (add is allowed only while no row exists) or `POST /api/clock/adjust/`.
  While absent, `GET /api/clock/` answers 503 `NOT_CONFIGURED` and every IC-date reader
  gets `None`; the ops dashboard's Required-content panel flags it as `game-clock`
  (`web/admin/tuning/required_content.py`, REQUIRED tier).

### GameClockHistory
Audit log for clock adjustments. Stores old/new anchor values, who changed it, and why.
- `change` — the kind (`ClockChange`: paused, resumed, speed, date_aged, date_kept; blank on
  rows from before #5248). The anchors alone cannot tell a pause from a change of date.
- `birth_year_shift` — years added to every character's birth year by a date set with ages
  kept; zero otherwise. Subtract it to undo that change by hand.

### ScheduledTaskRecord
Per-task tracking of last run time. Tasks are auto-created on first scheduler tick.
- `task_key` — unique string identifier
- `last_run_at` — real time of last execution
- `enabled` — staff can disable individual tasks via admin

## Calendar (#4185)

IC dates are plain Gregorian datetimes; the game's calendar is a naming layer over
them. `constants.IC_MONTH_NAMES` maps month 1-12 to Dreaming, Choosing, Thawing,
Waking, Rising, Vowing, Enduring, Gathering, Unyielding, Masquing, Keeping, Ending
(each reads as "the Month of ___"). Seasons, moons, birthdays and every stored date
are unaffected.

**Every IC date a player sees goes through these formatters**, never `strftime("%B")`,
`calendar.month_name` or the browser's `toLocaleDateString`:

| Helper | Output | Used by |
|---|---|---|
| `format_ic_date(dt)` | `Dreaming 14 (1/14/1012)` | `serializers.IcDateDisplayField` (events, journals, profile versions, recorded profiles); the relationship tie stream |
| `format_ic_month_day(m, d)` | `Dreaming 14 (1/14)` | birthdays (item_data, tidings, sheet identity) |
| `format_ic_date_long(dt)` | `the 14th of the Month of Dreaming, Year 1012` | clock API `date_display`, telnet `time` |
| `ic_month_name(m)` | `Dreaming` | clock API `month_name` |

The numeric date rides along on the inline forms because players won't remember the
names at first (ruled on #4185). Formatters read the date in UTC, as the clock does, so
a serializer's display zone can't move the day. The frontend keeps no copy of the
names: it renders the `*_display` strings, and the CG birthday picker reads
`ic_month_names` from the draft payload.

## Service Functions

### Clock Queries
- `get_ic_now()` — current IC datetime
- `get_ic_phase()` — TimePhase enum (DAWN, DAY, DUSK, NIGHT) with season-adjusted boundaries
- `get_ic_season()` — Season enum from IC month
- `get_light_level()` — float 0.0-1.0 for atmospheric lighting
- `get_ic_date_for_real_time(real_dt)` — convert real to IC datetime
- `get_real_time_for_ic_date(ic_dt)` — convert IC to real datetime

### Clock Management (staff)
- `set_clock(new_ic_time, changed_by, age_handling, reason="")` — set IC time (creates the
  clock or re-anchors it; see "Changing a clock that exists")
- `preview_clock_jump(new_ic_time)` — what that would do, as a `ClockJumpPreview`; writes nothing
- `set_time_ratio()` — change ratio with re-anchor
- `pause_clock()` / `unpause_clock()` — stop the clock; restart it from the date it shows

## Changing a clock that exists (#5248, ADR-5248)

Staff do this on the staff hub's **Game clock** page (`/staff/clock`,
`frontend/src/staff/clock/`): Pause, Resume from this date, Set the date, Change speed, and
a Recent changes list. **Every change goes through the four services**, which re-anchor the
clock and write `GameClockHistory`. The Django admin's change form is read-only for that
reason: saving `paused` or `time_ratio` there stored the field without moving the anchors,
so the date jumped (unticking Paused counted all the real time the clock had sat paused).
The admin still creates the one row.

**Resume counts nothing.** `unpause_clock` moves only the real-time anchor, so the clock
carries on from the date it showed. The date can be set while paused; it stays paused.

**A change of date is a jump, and `age_handling` says what it does to characters:**

| | `AgeHandling.AGED` | `AgeHandling.KEPT` |
|---|---|---|
| Birth years (`CharacterSheet.ic_birth_year`) | unchanged, so every age moves by the calendar years jumped | each moves by the calendar years jumped, so no age changes |
| The birthday task | walks the gap: matures each character by the birthdays skipped | skips the gap: every `ScheduledTaskRecord.last_ic_run_at` is set to the new time |
| Allowed for a change to an earlier date | no (`ClockError.EARLIER_KEEPS_AGES`): maturation does not go down | yes, and it is the only choice |

Both modes move every open dying window (`CharacterVitals.aging_death_ic_deadline`) and
every event still to come (`Event.scheduled_ic_time`, status draft or scheduled, real start
ahead) by the length of the jump. **A jump never kills anyone by itself**: without the first,
`run_death_sweep` would resolve every deadline a long jump passed. The monthly old-age check
runs once at the new date, not once per skipped month.

A jump never writes a heritage's `first_appeared_ic`, the IC dates already stamped on
journals, letters, recorded profiles, treatments and conditions (records, never compared for
logic), or anything timed in real time (condition expiry, letters in transit).

**Before #5248 a change to an earlier date stalled the aging tasks**: an IC-interval task is
due when `ic_now - last_ic_run_at >= interval`, which stayed negative until the calendar
passed the old date again. The re-stamp in `KEPT` is what ends that. After such a change a
birthday that falls between the new date and the old one happens again as time passes.

**Write contract.** `set_clock` runs in one transaction: the refusal and the history row
first (the steps that can fail; a rollback does not undo a change already made to an
identity-mapped instance), then the anchors and the task stamps changed in memory together,
then `vitals.aging.rebase_ages_for_clock_jump` and `events.services.shift_upcoming_events`.
Each loads the rows, changes the cached instances and writes them with
`bulk_update_with_reason`, so the instances the tasks read are the ones written.

Known and out of scope (#5250): population growth and sun exposure convert a stored real
time through the clock's current anchor, so they count a pause on resume and never see a jump.

## Scheduler

### GameTickScript (Evennia Script)
Persistent script that ticks every 5 minutes, calling `run_due_tasks()`.
Created automatically in `at_server_start()`, and **re-armed there too** (#4001):
`ensure_game_tick_script` checks `time_until_next_repeat()` and calls `start()` when
the row exists without a live timer. Evennia only restores a persistent script's
timer at boot from a `_paused_time` the previous graceful stop stored, so after any
hard kill the row stayed `db_is_active=True` with no timer, forever; production ran
that way from the 2026-08-23 SIGKILL recovery until #3993. The tick's first two
lines are its own safeguards: `close_old_connections()` (#3327, heals a dead
reactor-thread connection after a Postgres restart) and `rearm_maintenance_loop()`
(restarts Evennia's once-a-minute `server_maintenance` LoopingCall, which dies for
good when its runtime save raises). Neither runs unless the timer does, which is
what the boot-time re-arm guarantees; see `tools/agents/unarmed-safeguard-reviewer.md`.

### Task Registry
Tasks registered in `tasks.py` via `register_all_tasks()`, called at server startup.

### Execution Order — `CronPhase` (#2609)
`CronDefinition.phase` is the **ordering contract** for tasks that come due in the same
tick. `run_due_tasks()` sorts by it; the sort is stable, so registration order only
breaks ties *within* a band. Before #2609 ordering was emergent — a side effect of the
relative line numbers of two `register_task` calls — and nothing marked it load-bearing.

| Band | Value | For |
|------|-------|-----|
| `SNAPSHOT` | 100 | Pre-income baselines — read balances before anything moves them |
| `ECONOMY` | 200 | `weekly_rollover`: income, wages, debt service, contracts |
| `UPKEEP` | 300 | Building upkeep and personal recurring drains |
| `DRAIN` | 400 | Post-obligation purse drains (Somehow Always Broke, #2613) |
| `DEFAULT` | 500 | Everything with no ordering opinion (the default) |
| `CLEANUP` | 900 | Sweeps, decay, garbage collection |

Values are spaced so new bands can be inserted without renumbering.

**A phase only orders tasks that are already due together.** It does nothing on its own —
a task must also share an anchor with its neighbours for its band to ever come into play.
`buildings.weekly_upkeep` therefore carries *both* `phase=CronPhase.UPKEEP` and the
rollover's `anchor_weekday=0, anchor_hour_utc=5`.

`ECONOMY` before `UPKEEP` is deliberate and inverts the pre-#2609 accident: **income lands
before upkeep drains**, so a short player sees a smaller effective paycheck rather than an
unpreventable arrears hit and condition-tier slide. See
`docs/adr/0150-income-lands-before-upkeep.md`.

`SNAPSHOT`'s first member is `currency.purse_drain_snapshot` (#2613) — it records each
Somehow Always Broke holder's opening purse balance before income lands, which the `DRAIN`
band then drains down to. That two-band split is why `SNAPSHOT` and `DRAIN` bracket the
money bands rather than being one task.

### Wired Tasks
| Task | Frequency | Source App |
|------|-----------|------------|
| AP daily regen | 24h real | action_points |
| AP weekly regen | 7d real | action_points |
| Journal weekly reset | daily sweep | journals |
| Relationship weekly depth conversion | daily sweep | relationships (#3957) |
| Form expiration cleanup | hourly | forms |
| Condition expiration cleanup | hourly | conditions |
| Relationship temp-condition cleanup (Very Attracted drop-off) | hourly | relationships (#1697) |
| Block finalize (lifted-block clear) | hourly | scenes (#1278) |
| PoseSubmission ledger cleanup (`scenes.pose_submission_cleanup`) | hourly, `CLEANUP` | scenes (#3760) |
| Weather roll + echo | 2h real (≈6 IC h) | weather (#1522) |
| Gossip heat decay | 24h real | secrets (#1572) |
| Persona pursuit-heat decay | 24h real | justice (#1765) |
| Justice sentence sweep (`justice.sentence_sweep`) | 24h real | justice (#2378) |
| Sanctum resonance generation (`sanctum.resonance_generation_tick`) | 24h real | magic |
| Room ward upkeep (`room_features.ward_upkeep_tick`) | 24h real | room_features (#2177) |
| Weekly rollover (`weekly_rollover`) | weekly, Sun 00:00 EST anchor, `ECONOMY` | game_clock (#932) |
| Building upkeep sweep (`buildings.weekly_upkeep`) | weekly, same anchor, `UPKEEP` | buildings (#1930, #2609) |
| Purse drain snapshot (`currency.purse_drain_snapshot`) | weekly, same anchor, `SNAPSHOT` | currency (#2613) |
| Purse drain (`currency.purse_drains`) | weekly, same anchor, `DRAIN` | currency (#2613) |

(Table is partial — `register_all_tasks()` in `tasks.py` is the authoritative list.)

## API Endpoints

- `GET /api/clock/` — current IC time, phase, season, light level, `month_name`,
  `date_display`, `paused`, `time_ratio`, `month_names` (the twelve names, for a date picker)
- `GET /api/clock/convert/` — date conversion (IC<>real)
- `POST /api/clock/adjust/` — set IC time: `ic_datetime`, `reason`, `age_handling` (staff only)
- `GET /api/clock/adjust-preview/?ic_datetime=` — what that would do: direction, the year
  shift, characters with a birth year, upcoming events, heritages not yet appeared (staff only)
- `POST /api/clock/ratio/` — change time ratio: `ratio`, `reason` (staff only)
- `POST /api/clock/pause/` — pause clock (staff only)
- `POST /api/clock/unpause/` — resume from the date shown (staff only)
- `GET /api/clock/history/` — the recorded changes, newest first, paginated, `?change=` (staff only)

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
