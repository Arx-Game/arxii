# Location Substrate Polish — Design

**Status:** ready to implement (substrate completion; no novel design)
**Date:** 2026-05-12
**App home:** `world.locations`
**Depends on:** existing `world.locations` substrate (#432, #434, #435, #436)

## Why this exists

Four substrate PRs have shipped (ambient stats, ownership/tenancy,
permissions helpers, lifecycle helpers). Each design doc explicitly
deferred three small substrate-completion items:

- **A. Bulk read helpers** — `effective_stats_for_rooms`,
  `effective_owners_for_rooms`, `tenancies_for_rooms`. Foundation for
  any future "list all rooms with property X" surface (dashboards,
  where-command coloring, GM tools).
- **B. Modifier cleanup sweep** — periodic removal of
  `LocationStatModifier` rows whose `current_value()` has decayed to
  zero. Currently those rows accumulate forever.
- **C. Audit history helpers** — `ownership_history_for(location)` and
  `tenancy_history_for(location)`. Forensics / GM-tooling friendly
  reads of the full history including ended rows.

All three are well-defined from existing design docs. No new models, no
migrations, no novel decisions — purely substrate completion. Bundling
them into one PR because each is too small to warrant its own
brainstorm and they share the same patterns / test infrastructure.

## A — Bulk read helpers

### Shape

```python
def effective_stats_for_rooms(
    rooms: "Iterable[DefaultObject]",
    stat_keys: "Iterable[StatKey]",
) -> dict[int, dict[StatKey, int]]:
    """Bulk-resolve stats for many rooms in one pass.

    Returns: {room.pk: {stat_key: int}}.

    Performs one AreaClosure walk for the union of all ancestor area
    ids across rooms, one fetch of LocationStatOverride for those
    ids + room_profiles + stat_keys, one fetch of LocationStatModifier
    for the same scope, then resolves per room in Python.

    Rooms with no RoomProfile or no relevant rows fall through to
    STAT_DEFAULTS[stat_key] clamped to STAT_CLAMPS[stat_key].

    Query budget: 3 total queries regardless of room count
    (closure + overrides + modifiers).
    """


def effective_owners_for_rooms(
    rooms: "Iterable[DefaultObject]",
) -> dict[int, "LocationOwnership | None"]:
    """Bulk-resolve owners for many rooms in one pass.

    Returns: {room.pk: LocationOwnership | None}.

    One AreaClosure walk for the union of ancestor area ids, one fetch
    of active LocationOwnership rows for those ids + room_profiles
    (with select_related on area + holders), then most-specific-wins
    selection per room in Python.

    Query budget: 2 total queries regardless of room count.
    """


def tenancies_for_rooms(
    rooms: "Iterable[DefaultObject]",
) -> dict[int, list["LocationTenancy"]]:
    """Bulk-resolve currently-active tenancies for many rooms.

    Returns: {room.pk: [LocationTenancy, ...]}.

    One AreaClosure walk, one fetch of active LocationTenancy rows
    (with select_related on tenant_persona / tenant_organization /
    area), then group per room in Python.

    Note: returns a list per room (not a QuerySet), because grouping
    in Python after the bulk fetch precludes lazy evaluation.

    Query budget: 2 total queries regardless of room count.
    """
```

### Implementation outline

- Extract a private helper `_bulk_room_profiles_and_ancestors(rooms)`
  that returns `(room_to_profile: dict, profile_to_ancestor_ids: dict,
  all_ancestor_ids: set)`. Walks all `RoomProfile`s + one
  `AreaClosure` query covering the union of areas. One DB call total.
- Each bulk helper consumes that helper, fetches the relevant rows in
  one query, then groups/resolves per room in Python.
- Skips rooms with no `RoomProfile` (returns the appropriate empty:
  STAT_DEFAULTS for stats, None for owner, `[]` for tenancies).

### Tests

- Empty iterable → empty dict
- Single room → matches the singular helper's result for that room
- Multiple rooms with mixed structure (some with overrides, some with
  modifiers, some with no rows) — each room gets correct result
- Query-budget enforcement via `assertNumQueries` (3 for stats, 2 for
  owners, 2 for tenancies)
- Room without RoomProfile → falls through cleanly (no exception)
- Caller passes empty `stat_keys` → returns `{room.pk: {}}`

## B — Modifier cleanup sweep

### Shape

```python
def cleanup_decayed_modifiers(now: "datetime | None" = None) -> int:
    """Delete LocationStatModifier rows whose current_value() has
    decayed to zero.

    Iterates rows with non-zero change_per_day (zero-rate rows never
    decay), computes current_value() in Python (matching the read-side
    semantics), and deletes those that have crossed zero.

    Returns the count of rows deleted.

    Cheap to call from a cron or management command on any cadence —
    rows that haven't decayed yet are skipped without write traffic.

    The caller may pass `now` to make the sweep deterministic for
    tests; otherwise defaults to `timezone.now()`.
    """
```

### Management command

`src/world/locations/management/commands/cleanup_decayed_modifiers.py`:
- Thin wrapper that calls `cleanup_decayed_modifiers()` and prints the
  count. Usable as `arx manage cleanup_decayed_modifiers`.

### Why Python-side computation, not SQL

`LocationStatModifier.current_value()` is in-memory math involving the
applied_at delta. Replicating it in SQL would mean a CASE expression
that nobody can audit. Python-side is identical to the read-side
semantics, the table is small (modifiers per location are rare), and a
sweep is a once-per-day operation — speed isn't critical.

### Tests

- Row with `change_per_day=0` is NOT deleted (no decay)
- Row whose `current_value()` is non-zero is NOT deleted
- Row whose `current_value()` has crossed to 0 IS deleted
- Returns the correct deletion count
- Mixed batch — only crossed rows deleted, others remain
- Caller-supplied `now` is honored
- Management command runs and prints the count

### Cron / scheduling

Out of scope for v1 — this PR ships the function and the management
command. Wiring it into a real scheduled job is a separate concern
(could be cron, Celery beat, Evennia's TickerHandler, etc.). The
function is idempotent and safe to call manually until then.

## C — Audit history helpers

### Shape

```python
def ownership_history_for(
    *,
    area: "Area | None" = None,
    room_profile: "RoomProfile | None" = None,
) -> "QuerySet[LocationOwnership]":
    """Return ALL LocationOwnership rows (including ended) for the
    given location, ordered by acquired_at ascending.

    Includes the current active row (if any) at the end of the
    sequence. Walks no closure — returns only rows directly attached
    to this location. Caller passes one of (area, room_profile).

    Useful for forensics, GM tooling, and audit log displays.
    """


def tenancy_history_for(
    *,
    area: "Area | None" = None,
    room_profile: "RoomProfile | None" = None,
) -> "QuerySet[LocationTenancy]":
    """Return ALL LocationTenancy rows (including ended) for the
    given location, ordered by started_at ascending.

    Walks no closure — returns only rows directly attached to this
    location. Caller passes one of (area, room_profile).
    """
```

### Why no closure walk

The history is per-target-row, not per-cascade. If the question is
"who has owned this manor (Building)," the answer is the ownership
rows directly on that Building — not rows on the Ward or City above
it. Those upstream rows are part of a different audit story.

Callers that want the full cascade history can call this helper on
each level of the closure themselves.

### Validation

Reuse `_validate_location_kwargs(area, room_profile)` — same
exactly-one semantics. No holder validation needed (no holder
parameter on the history helpers).

### Tests

- Returns all rows for a location, ordered by acquired_at / started_at
- Includes both active and ended rows
- Excludes rows on unrelated locations
- Empty iterable when no rows exist
- Validation: missing both / passing both → ValueError
- Returns `LocationOwnership` (not `LocationTenancy`) from
  `ownership_history_for` and vice versa for `tenancy_history_for`

## File layout

- Append to `src/world/locations/services.py`:
  - `_bulk_room_profiles_and_ancestors(rooms)` private helper
  - `effective_stats_for_rooms`
  - `effective_owners_for_rooms`
  - `tenancies_for_rooms`
  - `cleanup_decayed_modifiers`
  - `ownership_history_for`
  - `tenancy_history_for`
- Create `src/world/locations/management/__init__.py` (empty)
- Create `src/world/locations/management/commands/__init__.py` (empty)
- Create `src/world/locations/management/commands/cleanup_decayed_modifiers.py`
- Append tests in `src/world/locations/tests/test_bulk_reads.py`,
  `src/world/locations/tests/test_cleanup.py`,
  `src/world/locations/tests/test_history.py`
- Update `src/world/locations/CLAUDE.md` with three new sections

## What this PR explicitly defers

- **Cron / scheduling for `cleanup_decayed_modifiers`** — wiring is
  separate from the function. Can run manually or via `just` recipe
  until a cron exists.
- **Stat-driven DC modifier consumer (D in the menu)** — a real
  consumer of the substrate; deserves its own brainstorm + PR.
- **DRF permission classes** — when API consumers materialize.
- **Discovery-aware permission helper** — needs PersonaDiscovery
  integration design.
- **Bulk variants of permission helpers** (`is_owner_of_any`, etc.) —
  add when consumers want them.

## Cross-cutting notes

- All helpers are type-annotated (typed app).
- No new models, no migrations.
- All bulk helpers operate via the SharedMemoryModel identity map for
  any subsequent attribute walks (consumer-side concern).
- Tests cover query budgets via `assertNumQueries` per project policy.
