# Locations - Ambient Value Cascade

Authored substrate for room/area values that cascade through the area
hierarchy. Carries two axis types in one cascade:

- **Stat axis** — ambient stats (crime, order, lighting, …) keyed on a
  `StatKey` TextChoices enum.
- **Resonance axis** — magical resonance magnitudes per room, keyed on a
  FK to `magic.Resonance`. Replaces the former `RoomAuraProfile` /
  `RoomResonance` tag system from Spec C.

A single read service (`effective_value`) resolves either axis.

See `docs/plans/2026-05-09-location-stats-design.md` for the original
cascade design and `docs/plans/2026-05-14-room-cascade-resonance-unification.md`
for the resonance axis addition.

## Models

- **`LocationValueOverride`** — absolute claim at a specific area or room.
  Most-specific override in the cascade chain wins, and any override
  anywhere in the chain causes ALL modifiers in that chain to be ignored.
  **Use rarely** — for warded sanctums, safehouses, magically stabilized
  chambers. The "this is the value, period" claim.
- **`LocationValueModifier`** — additive contribution. Stacks across the
  cascade chain. Carries `change_per_day` for read-time decay/growth.
  **The common authoring path** — including for what feels like
  "the permanent value at this level," which is just a modifier with
  `change_per_day=0`.

Both models inherit from `core.mixins.DiscriminatorMixin` and
`evennia.utils.idmapper.models.SharedMemoryModel`. They use two
discriminators:

- `parent_type` (AREA or ROOM) — selects `area` vs `room_profile` FK.
- `key_type` (STAT or RESONANCE) — selects `stat_key` (CharField from
  `StatKey`) vs `resonance` (FK to `magic.Resonance`).

Exactly one of each discriminator pair is populated per row, enforced by
`clean()` which calls `DiscriminatorMixin._validate_discriminator` once
per pair. `_validate_discriminator` treats `None` and `""` as both unset,
so the stat_key CharField (default `""`) works alongside the resonance FK.

## Cascade rule

For any `(room, axis_key)`:

1. Walk the closure chain from the room outward via `world.areas.AreaClosure`.
2. **If any level in the chain has authored an Override for the matching axis** → use the
   most-specific Override's value (clamped for stats only). All Modifiers ignored.
3. **Otherwise** → sum every Modifier's `current_value()` across the
   chain for the matching axis. Stats add `STAT_DEFAULTS[stat_key]` and
   clamp to `STAT_CLAMPS[stat_key]`; resonance starts from 0 and is not
   clamped.

`AreaClosure` includes self at depth 0, so a Room's own area is in the
ancestor set.

## Authoring discipline

- Default to **Modifier**. Most authored values — even ones that feel
  static, like a noble manor's prestige — should be a Modifier with
  `change_per_day=0`. They're called "modifiers" but they're equally
  valid as authored baselines that happen to never change.
- Reach for **Override** only when you mean "ignore everything upstream
  and downstream — this is the value." If you find yourself authoring
  Overrides routinely, you're probably misusing them.
- Use the `source` field on Modifiers when the originating system needs
  to clean up later: `LocationValueModifier.objects.filter(source="rebellion_1234").delete()`.
- `change_per_day` is signed: negative decays toward zero, positive grows
  away from zero, zero is permanent. `current_value()` clamps to zero
  once a modifier crosses its original sign — eligible for cleanup but
  inert until then.

## Reading

Polymorphic single-axis read:

```python
from world.locations.services import effective_value
from world.locations.constants import StatKey
from world.magic.models import Resonance

# Stat axis
crime_here = effective_value(room, stat_key=StatKey.CRIME)

# Resonance axis (e.g. cathedral celestial intensity)
copperi = Resonance.objects.get(name="Copperi")
celestial_here = effective_value(room, resonance=copperi)
```

Exactly one of `stat_key` or `resonance` must be provided.

For per-room "is this room tagged with resonance X" gates (e.g. residence
trickle), prefer a direct query on `LocationValueModifier` rows rather
than calling `effective_value` — the cascade walk is overkill if you only
care about what the room itself emits. See `world.magic.services.gain.get_residence_resonances`
for the pattern.

Bulk variant:

```python
from world.locations.services import effective_values_for_rooms

stats = effective_values_for_rooms(rooms, stat_keys=[StatKey.CRIME, StatKey.NOISE])
resonances = effective_values_for_rooms(rooms, resonances=[copperi, predari])
```

## Adding a new stat

1. Add a member to `StatKey` in `constants.py`.
2. Add entries to `STAT_DEFAULTS`, `STAT_CLAMPS`, `SUGGESTED_CHANGE_PER_DAY`.
3. Run `echo "yes" | uv run arx manage makemigrations locations` —
   TextChoices changes emit a Django migration that's a no-op at the DB
   level (the `choices=` kwarg lives in Python, not the column).
4. Run `arx manage migrate locations`.

## Integration notes

- Stats live separately from `world.mechanics` modifier targets (which
  apply to character traits, not locations). Same conceptual pattern,
  parallel implementation.
- The cascade reads use `select_related("area")` so a single override
  resolution stays at 2 queries (closure + override fetch). Modifier path
  is also 2 queries (closure + modifier fetch); modifier `current_value()`
  is in-memory math.
- Trust the SharedMemoryModel identity map. Do NOT build resolve_/batch_
  helpers around stats — repeated reads within a request reuse cached
  instances. See the project's auto-memory note on identity-map discipline.

## Authoring caveats

- Always create rows via `objects.create()` (or the manager). The
  DiscriminatorMixin's `clean()` runs only via `full_clean()` and the
  `save()` override. `bulk_create` and raw SQL inserts skip validation
  and could leave `parent_type` inconsistent with the FKs.
- `applied_at` defaults to `timezone.now` at instance construction, not
  at save time. If you build a row and persist later, the decay anchor
  reflects construction. To "refresh" a modifier (reset its decay clock),
  set `applied_at = timezone.now()` and `save()`.

## Ownership and Tenancy (added 2026-05-10)

Two additional models capture *who holds the deed* and *who has been granted
use* of a location. Designed in `docs/plans/2026-05-10-location-ownership-tenancy-design.md`.

### Models

- **`LocationOwnership`** — deed/title holder. Cascades through the area
  hierarchy: most-specific active row wins. Liege/vassal nesting is
  multiple rows at different tiers, naturally resolved by the cascade.
- **`LocationTenancy`** — granted, time-bound, revocable use right. Does
  NOT follow most-specific-wins. The reader collects ALL applicable rows
  (room-level + ancestor-area-level). Multiple concurrent tenancies
  are valid (married couples, roommates, communal bunkrooms).

Both models use the existing `LocationParentType` for the parent
discriminator (Area XOR Room) and a new `HolderType` for the holder
discriminator (Persona XOR Organization). Each model's `clean()` calls
`DiscriminatorMixin._validate_discriminator()` once per discriminator
and merges errors so all field errors surface together.

### Reading

```python
from world.locations.services import effective_owner, current_tenants

ownership = effective_owner(room)  # LocationOwnership | None
if ownership is not None:
    holder = ownership.get_active_target()  # Persona or Organization

for tenancy in current_tenants(room):
    tenant = tenancy.get_active_target()
```

Both services share the `_room_profile_and_ancestors(room)` helper which
walks `AreaClosure` once and returns `(profile, ancestor_ids)`.
`effective_owner` uses most-specific-wins selection; `current_tenants`
returns a `QuerySet` filtered for `ends_at IS NULL OR ends_at > now()`.

### Authoring discipline

- Use `ended_at` to retire an Ownership row (transfer, abandonment); do not
  delete. The audit trail is the history.
- **Until a `transfer_ownership` helper exists**, wrap ownership transfers
  in `transaction.atomic`: set `ended_at = now()` on the old row, save it,
  then create the new row. The partial-unique constraint requires the
  old row's commit to land first, and an atomic block prevents a
  concurrent reader from seeing "no active owner."
- For Tenancy, set `ends_at` (planned end OR moment of eviction) to
  retire a row. Keep the row.
- The partial-unique constraint enforces only ONE active Ownership per
  location. Multiple active Tenancies are allowed and expected.
- Most authoring goes through the lifecycle helpers (see below). Direct
  `objects.create()` is fine for test fixtures, but production code uses
  the helpers so the partial-unique + transactional protocol stays in
  one place.

## Relationship lookups (added 2026-05-11)

Four helpers answer "does this persona have owner / tenant standing at
this room?" — the canonical first consumer of the Ownership and Tenancy
substrate. Specific permission checks (`can_decorate`, `can_evict`,
`can_install`, etc.) live in their consuming systems where the rules
naturally belong.

```python
from world.locations.services import (
    ownership_for,
    is_owner,
    tenancies_for,
    is_tenant,
)

# Returns the LocationOwnership row, or None
row = ownership_for(persona, room)

# Same but boolean
if is_owner(persona, room):
    ...

# QuerySet of currently-active tenancies that give this persona standing
for tenancy in tenancies_for(persona, room):
    ...

if is_tenant(persona, room):
    ...
```

### Standing rules

A persona has **owner standing** when:

- The cascade-resolved owner is this persona directly, OR
- The cascade-resolved owner is an Organization this persona is a current
  member of (any rank)

A persona has **tenant standing** when:

- An active LocationTenancy for the room or an ancestor area has
  `tenant_persona = this persona`, OR
- An active tenancy targets an Organization this persona is a current
  member of (any rank)

The helpers do NOT consider rank — downstream systems gate on
`OrganizationMembership.rank` themselves.

The helpers are **strictly per-persona**. This covers two distinct
cases with different rationales:

- **alt_personas** (same `CharacterSheet`, different Persona): OOC the
  character owns the room, but the secondary persona is *secret* by
  design — house guards / servants treat it as an intruder until the
  persona link is discovered. Substrate reflects the IC default; a
  discovery-aware downstream check can compose on top.
- **alt_characters** (same Account, different `CharacterSheet`):
  different characters, no shared standing under any circumstance. The
  Account link is OOC bookkeeping only.

Don't confuse this with the no-alt-outing hard rule — that's about
*display* (never expose Account-level character links). Access checks
are a separate concern.

### Query budgets

- `is_owner` / `ownership_for` with PERSONA-holder match: **2 queries**
  (the org_ids fetch is short-circuited via early return)
- `is_owner` / `ownership_for` with ORGANIZATION-holder match: **3 queries**
- `is_tenant` / `tenancies_for`: **3 queries** (org_ids + closure walk
  + tenancy fetch)

Budgets are locked via `assertNumQueries` tests.

## Lifecycle write helpers (added 2026-05-11)

Three helpers in `world.locations.services` wrap the partial-unique +
transactional protocol so callers don't have to reimplement it:

```python
from world.locations.services import (
    transfer_ownership,
    grant_tenancy,
    end_tenancy,
)

# Atomic transfer or claim — ends current owner (if any), creates new row
transfer_ownership(area=ward, to_organization=house_stark, notes="conquest")

# Single-insert new tenancy — no conflict check
grant_tenancy(room_profile=apartment, tenant_persona=traveler, ends_at=next_week)

# Single-update setting ends_at — covers eviction and voluntary departure
end_tenancy(tenancy)
```

`transfer_ownership` wraps the end-existing + create-new sequence in
`transaction.atomic` so concurrent readers never see a "no active owner"
window. It also calls `select_for_update` on the existing-row lookup so
concurrent transfers on the same parent serialize cleanly (T2 waits for
T1's commit). Concurrent *claims* of a never-owned location still race
at the INSERT and rely on the partial-unique constraint to surface
`IntegrityError` to the loser — rare contention in practice.

**Permission gating is the caller's concern.** These helpers do not
call `is_owner` or check authority. Consumers must gate access first
(via `is_owner`, `OrganizationMembership.rank`, etc.) before invoking
them.

## Bulk read helpers (added 2026-05-12)

Three bulk variants of the singular cascade readers, for surfaces that
need to resolve many rooms at once (where-command coloring, dashboards,
list views).

```python
from world.locations.services import (
    effective_stats_for_rooms,
    effective_owners_for_rooms,
    tenancies_for_rooms,
)

# {room.pk: {stat_key: int}}
stat_map = effective_stats_for_rooms(rooms, [StatKey.CRIME, StatKey.LIGHTING])

# {room.pk: LocationOwnership | None}
owner_map = effective_owners_for_rooms(rooms)

# {room.pk: list[LocationTenancy]}  (list, not QuerySet — see below)
tenant_map = tenancies_for_rooms(rooms)
```

All three share a private `_bulk_room_profiles_and_ancestors(rooms)`
helper that batches `RoomProfile` resolution and emits ONE
`AreaClosure` query for the union of areas. Per-room resolution
happens in Python.

### Query budgets

- `effective_stats_for_rooms`: **4 queries** (profiles + closure + overrides + modifiers)
- `effective_owners_for_rooms`: **3 queries** (profiles + closure + active ownership rows)
- `tenancies_for_rooms`: **3 queries** (profiles + closure + active tenancy rows)

All budgets are independent of room count (one bulk SQL query per kind
of row) and locked via `assertNumQueries` tests.

### Why `tenancies_for_rooms` returns a list, not a QuerySet

Grouping in Python after the bulk fetch precludes lazy evaluation —
the rows are already materialized once. Returning a list per room is
honest about that. The singular `current_tenants` still returns a
QuerySet because it doesn't need to group.

### Rooms without a RoomProfile

Fall through cleanly:

- `effective_stats_for_rooms` → `{stat_key: STAT_DEFAULTS[stat_key]_clamped}` for each requested stat
- `effective_owners_for_rooms` → `None`
- `tenancies_for_rooms` → `[]`

## Cleanup sweep (added 2026-05-12)

`LocationValueModifier` rows whose `current_value()` has decayed to
zero accumulate forever without a sweep. The service that prunes them:

```python
from world.locations.services import cleanup_decayed_modifiers

# Returns the count of rows deleted
deleted = cleanup_decayed_modifiers()

# Caller may supply `now` to make the sweep deterministic
deleted = cleanup_decayed_modifiers(now=some_datetime)
```

Iterates rows with non-zero `change_per_day`, computes `current_value()`
in Python (matching read-side semantics), deletes those that have
crossed zero. Static (zero-rate) modifiers are never touched.

### Management command

```bash
arx manage cleanup_decayed_modifiers
```

Prints the count of deleted rows.

### Cron / scheduling

Not wired in v1. Run manually, via `just`, or hook up a scheduled job
later. The function is idempotent.

## Audit history helpers (added 2026-05-12)

Two read-only services that return the full history of a location's
ownership / tenancy rows (active + ended), ordered ascending by
`acquired_at` / `started_at`. Useful for forensics, GM tooling, and
audit log displays.

```python
from world.locations.services import ownership_history_for, tenancy_history_for

# QuerySet[LocationOwnership], oldest first, includes ended rows
for row in ownership_history_for(area=manor):
    ...

# QuerySet[LocationTenancy], same shape
for row in tenancy_history_for(room_profile=apartment):
    ...
```

### No closure walk

History is **per-target-row**, not per-cascade. If you want the
ownership history of the manor and the ward it sits in, call this on
each level yourself. The substrate doesn't conflate those audit
stories.

### Validation

Same `_validate_location_kwargs` shape as the lifecycle helpers —
exactly one of `area` or `room_profile`. Raises `ValueError` on
violation.
