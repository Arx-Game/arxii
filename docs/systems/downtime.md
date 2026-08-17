# Downtime Announcements

Scheduled-downtime announcements (#3194). Players get warned before the game
goes down — both for staff-planned maintenance and for the host's automatic
security reboot, which previously happened unannounced (2026-08-16: a kernel
update rebooted prod at 04:30 UTC with the schedule known 22 hours ahead and
no way to tell anyone).

**Source:** `src/world/downtime/`
**API prefix:** `/api/downtime/`

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DowntimeWindow` | Staff-declared maintenance window, authored in the admin | `starts_at`, `expected_duration_minutes`, `message` (player-facing), `created_by`, `canceled_at` |

The automatic host reboot is deliberately **not** stored as a row. It is
derived live from systemd's scheduled-shutdown file, so the same fact is never
typed twice and the warning disappears by itself if the reboot is canceled.

## Service functions (`world.downtime.services`)

- `get_next_downtime() -> PlannedDowntime | None` — the soonest upcoming or
  in-progress downtime, merging two sources:
  - the next un-canceled `DowntimeWindow` whose end has not passed (48h
    lookback bounds the scan while catching in-progress windows);
  - the host's scheduled reboot, parsed from
    `settings.SCHEDULED_SHUTDOWN_FILE` (default
    `/run/systemd/shutdown/scheduled` — systemd writes it when a
    shutdown/reboot is scheduled, removes it on cancel; `USEC` is epoch
    microseconds). Any parse problem yields None: a broken warning must never
    break the status API. Derived windows use `DowntimeSource.SYSTEM`, a
    5-minute expected duration, and fixed banner copy (`constants.py`).

`PlannedDowntime` (`types.py`) is the frozen dataclass return shape.

## API

| Endpoint | Method | Access | Purpose |
|---|---|---|---|
| `/api/downtime/next/` | GET | Public | `{"downtime": null}` or `{"downtime": {source, starts_at, expected_duration_minutes, message}}` |

## Frontend

`frontend/src/components/DowntimeBanner.tsx`, mounted globally in `Layout`
(the `SeanceOfferBanner` pattern): polls the endpoint every 5 minutes so a
window scheduled while a page sits open still shows up, renders when the
window is within 24 hours or in progress, and switches to "Maintenance in
progress" copy once `starts_at` passes. Anonymous-safe; a failed poll renders
nothing rather than breaking the page.

## Not built (deliberate)

- **Telnet / in-game push announcements** as the window approaches — the web
  banner is the primary surface (web-first architecture); a scheduled
  broadcast to connected sessions is separable work if telnet parity is ever
  wanted here.
- **Shortening the reboot outage itself** (the 90s first-start timeout on
  2026-08-16) — explicitly out of scope in #3194.
