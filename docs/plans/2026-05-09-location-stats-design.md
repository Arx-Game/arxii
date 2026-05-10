# Location Ambient Stats — Cascade Substrate Design

**Status:** validated brainstorm; ready to implement
**Date:** 2026-05-09
**App home:** `world.locations` (new app)
**Depends on:** `world.areas` (Area, AreaClosure), `evennia_extensions` (RoomProfile),
`core.mixins.DiscriminatorMixin`

## Why this exists

The 2026-05-06 player-and-GM-experience brainstorm flagged room state tracking as
a load-bearing system: rooms have ambient stats (crime, order, cleanliness,
lighting, …) that drive ambient encounter generation, modify check difficulty,
and emerge from aggregate PC actions over time. The brainstorm noted "named;
full taxonomy unknown" and tagged it as needing its own roadmap stub.

This design provides the *substrate* — the data model, cascade resolution, and
single read service — that every consuming system (encounter generator, DC
modifier, where-command coloring, weather system, magic system, events bonuses)
will plug into. It is intentionally narrow: cascade math + minimal authoring.

It is **not** a design for ownership, room installations (research labs,
arenas, vaults), decoration loops, or room-as-investable-feature. Those are
separate larger systems flagged for follow-up brainstorms.

## Bedrock decisions

### Cascade rule

Rooms inherit stats from the area hierarchy
(`Building → Neighborhood → Ward → City → Region → Kingdom → Continent → World →
Plane`, walked via the existing `AreaClosure` materialized view).

For any `(room, stat_key)`:

1. Walk the closure chain from the room outward.
2. **If any level in the chain has authored an `Override` for `stat_key`** →
   use the **most-specific** Override's value (clamped to the stat's bounds).
   All Modifiers in the chain are ignored. Done.
3. **Otherwise** → sum every Modifier's `current_value()` for `stat_key` across
   the chain, plus the per-stat default. Clamp to bounds.

Overrides are deliberate "cut the cascade" claims (the safehouse, the magically
warded sanctum, the absolute-no-crime-here statement). They are used **rarely**.

Modifiers are the common authoring path — including for what feels like
"the permanent value at this level," which is expressed as a Modifier with
`change_per_day=0`.

### Volatility uses the same schema

High-churn stats (crime, order, cleanliness, traffic) and low-churn stats
(prestige, comfort, fashion when added later) share the same model. The
difference is row volume and authoring frequency, not structure.

### Per-row decay/growth

Each Modifier carries its own `change_per_day` (signed integer, default 0).
- Negative → magnitude shrinks toward 0 (decay)
- Positive → magnitude grows away from 0 (e.g., wealth accumulating)
- 0 → static; row exists indefinitely until a system deletes it

Decay/growth is computed lazily at read time from `applied_at` — no write
storms, no scheduled job in v1.

### Source labels for system attribution

Modifiers carry an optional `source` text label so originating systems can
clean up their own rows by source when their event ends. v1 has no
convenience helper for this; callers run
`LocationStatModifier.objects.filter(source='rebellion_1234').delete()`.

## Models

```python
# world/locations/constants.py

class StatKey(models.TextChoices):
    CRIME = "crime", "Crime"
    ORDER = "order", "Order"
    CLEANLINESS = "cleanliness", "Cleanliness"
    LIGHTING = "lighting", "Lighting"
    NOISE = "noise", "Noise"
    TRAFFIC = "traffic", "Traffic"

STAT_DEFAULTS: dict[str, int] = {
    StatKey.CRIME: 0,
    StatKey.ORDER: 50,
    StatKey.CLEANLINESS: 50,
    StatKey.LIGHTING: 0,         # signed: -2 dark to +2 bright
    StatKey.NOISE: 50,
    StatKey.TRAFFIC: 50,
}

STAT_CLAMPS: dict[str, tuple[int, int]] = {
    StatKey.CRIME: (0, 100),
    StatKey.ORDER: (0, 100),
    StatKey.CLEANLINESS: (0, 100),
    StatKey.LIGHTING: (-2, 2),
    StatKey.NOISE: (0, 100),
    StatKey.TRAFFIC: (0, 100),
}

# Used by services as the *suggested* default when authoring modifiers; the
# value can be overridden per-row to reflect IC mechanics that govern decay
# or growth rate.
SUGGESTED_CHANGE_PER_DAY: dict[str, int] = {
    StatKey.CRIME: -1,
    StatKey.ORDER: 0,
    StatKey.CLEANLINESS: -1,
    StatKey.LIGHTING: 0,
    StatKey.NOISE: -2,
    StatKey.TRAFFIC: -1,
}
```

```python
# world/locations/models.py

class LocationStatOverride(SharedMemoryModel, DiscriminatorMixin):
    """An absolute claim about a stat at a specific area or room.

    Most-specific override in the cascade chain wins. Overrides cut the
    cascade entirely: when any override exists at any level above (or equal
    to) the room, all modifiers are ignored.

    Use sparingly — for warded sanctums, safehouses, magically stabilized
    chambers, or other deliberate 'this is the value, period' claims.
    """
    area = models.ForeignKey("areas.Area", null=True, blank=True, on_delete=CASCADE,
                              related_name="stat_overrides")
    room_profile = models.ForeignKey("evennia_extensions.RoomProfile",
                                     null=True, blank=True, on_delete=CASCADE,
                                     related_name="stat_overrides")
    stat_key = models.CharField(max_length=50, choices=StatKey.choices, db_index=True)
    value = models.IntegerField()
    last_updated = models.DateTimeField(auto_now=True)

    # DiscriminatorMixin enforces: exactly one of (area, room_profile) is set.

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["area", "stat_key"],
                condition=models.Q(area__isnull=False),
                name="unique_override_per_area_stat",
            ),
            models.UniqueConstraint(
                fields=["room_profile", "stat_key"],
                condition=models.Q(room_profile__isnull=False),
                name="unique_override_per_room_stat",
            ),
            # DiscriminatorMixin contributes the area-XOR-room_profile check.
        ]


class LocationStatModifier(SharedMemoryModel, DiscriminatorMixin):
    """An additive contribution to a stat at a specific area or room.

    Modifiers stack across the cascade chain. The effective value at a room
    is the sum of every modifier's current value, plus the per-stat default,
    clamped to bounds — provided no override exists in the chain.

    Carries its own change_per_day so consuming systems can model decay or
    growth rates that depend on IC mechanics. Read-time math is lazy:
    current_value = value + change_per_day * days_since(applied_at).
    """
    area = models.ForeignKey("areas.Area", null=True, blank=True, on_delete=CASCADE,
                              related_name="stat_modifiers")
    room_profile = models.ForeignKey("evennia_extensions.RoomProfile",
                                     null=True, blank=True, on_delete=CASCADE,
                                     related_name="stat_modifiers")
    stat_key = models.CharField(max_length=50, choices=StatKey.choices, db_index=True)
    value = models.IntegerField()  # magnitude at applied_at
    change_per_day = models.IntegerField(default=0)
    source = models.CharField(max_length=200, blank=True)
    applied_at = models.DateTimeField(default=timezone.now)

    def current_value(self, *, now: datetime | None = None) -> int:
        """Lazy decay/growth math. Returns 0 once the modifier has crossed its
        original sign (decayed-positive past 0, or grown-negative past 0)."""
        if self.change_per_day == 0:
            return self.value
        anchor = now or timezone.now()
        days = (anchor - self.applied_at).total_seconds() / 86400
        drift = int(self.change_per_day * days)
        new_value = self.value + drift
        # Clamp at zero crossing — modifier becomes inert past its zero
        if self.value > 0 and new_value < 0:
            return 0
        if self.value < 0 and new_value > 0:
            return 0
        return new_value
```

`RoomProfile` gains:
```python
is_outdoor = models.BooleanField(
    default=False,
    help_text="Whether this room is exposed to outdoor environment "
              "(weather, sky, etc.). Most rooms are indoor.",
)
```

## Read service

Single function, single signature:

```python
# world/locations/services.py

def effective_stat(room: ObjectDB, stat_key: StatKey) -> int:
    """Cascade-resolve a single stat for a room, clamped to per-stat bounds.

    Algorithm:
      1. Resolve room.room_profile and room_profile.area. If either is missing,
         start from the area-less branch (just default + clamp).
      2. Look up the closure ancestors of room_profile.area via AreaClosure.
      3. Query LocationStatOverride for any matching (area in closure or
         room_profile == this room) AND stat_key. If any rows exist, pick the
         one with maximum specificity (room > more-specific area > less-
         specific area), clamp, return.
      4. Otherwise, query LocationStatModifier for the same closure scope and
         stat_key. Sum current_value() across rows.
      5. Add STAT_DEFAULTS[stat_key]. Clamp to STAT_CLAMPS[stat_key]. Return.

    Per-call query budget: 2-3 (closure ancestors, override, modifier).
    Repeated calls within a request reuse SharedMemoryModel-cached instances.
    """
```

That's the entire v1 service surface.

## What v1 ships

- `world.locations` app (registered, type-checked)
- `LocationStatOverride` and `LocationStatModifier` models with constraints
- `StatKey` TextChoices + per-stat constants in `constants.py`
- `is_outdoor` BooleanField on `RoomProfile` (one-line migration)
- `effective_stat(room, stat_key)` service
- Auto-generated Django admin with help text on Override-vs-Modifier discipline
- Factories for both models
- Tests: cascade rule, decay/growth math, partial-unique constraints,
  DiscriminatorMixin enforcement, default fallback, is_outdoor field
- A short `world/locations/CLAUDE.md` documenting authoring discipline

## What v1 explicitly defers

| Item | When to add |
|---|---|
| `effective_stats(room, stat_keys)` (multi-stat per room) | When a serializer renders many stats and per-call query overhead matters |
| `effective_stats_for_rooms(rooms, stat_keys)` (bulk) | When the where-command or similar surface needs per-room stat coloring |
| `explain_stat(room, stat_key)` (debug breakdown) | When staff start asking "why is crime 45 here" |
| Convenience write helpers (`add_modifier`, `refresh_modifier`, etc.) | When repeated patterns emerge — one-line `.objects.create()` is fine until then |
| `cleanup_decayed_modifiers()` sweep | When row growth becomes measurable; decayed rows return 0 from `current_value` so they're inert |
| `authored_by_account` audit field | When staff want attribution; trivial migration when the need lands |
| API exposure (REST endpoints, frontend) | When a frontend consumer materializes |
| Cron schedule for cleanup | After the cleanup function exists |
| Per-affinity magical stats (resonance per affinity, ley strength, sacred intensity) | Land with the magic system's room-aware features |
| Aesthetic stats (prestige, comfort, fashion) | Land with the events bonuses + decoration loops |
| Weather stats (temperature, humidity, exposure) | Land with the weather system; written from there onto region-level Modifiers |
| Economic / political stats (wealth, loyalty, unrest) | Land with the missions / society systems |
| Convert `AreaLevel` IntegerChoices to a model | Only if a real need to insert new tier types emerges |

## Out of scope — separate brainstorms needed

These were surfaced during the brainstorm but are large enough to deserve
their own design passes:

### Ownership (personal + organizational + tenancy)

Rooms, buildings, and higher tiers can be owned by:
- A **character** (Persona / RosterEntry)
- An **organization** (noble house, adventuring party / covenant, crime
  family, guild, …)

Ownership at one tier can confer **assignment rights** at finer tiers:
- A noble house owns the manor (building); the head of house assigns a
  bedroom to a noble (room); the bedroom is "owned" by the noble in the
  sense that they have IC affordances over it, but the building owner
  retains override authority and can revoke / reassign.
- Same model covers apartment rentals (landlord owns building, tenant has
  rights over a unit, landlord can evict) and inn rooms (innkeeper owns
  building, traveler has temporary rights to a room).

Implications:
- The model needs to express **owner-of-record** and **assigned-occupant**
  separately, with the latter time-bound (lease, tenancy term, indefinite
  with revocation).
- Polymorphic ownership (character XOR organization-of-various-types) likely
  uses the same `DiscriminatorMixin` pattern, but the org side spans multiple
  apps that don't all exist yet (covenants partially shipped; noble house and
  crime family entities don't yet have entities).
- IC affordances unlocked by ownership/assignment (decoration permissions,
  vault access, servant assignment, defense installation rights) are downstream
  consumers — they consult ownership state when checking permissions.

### Room installations (each is its own gameplay system)

Items #8 from the original room-state enumeration — installed features that
transform a room into a system-bearing space:

- **Defenses** → invasion / break-and-enter / home defense gameplay
- **Anti-spy installations** → espionage gameplay loop
- **Research stations** → codex entry research & lore discovery
- **Combat arenas** → sparring-tier combat
- **Forges / alchemy benches / libraries** → crafting bonuses
- **Lairs / hideouts** → criminal organization gameplay
- **Vaults** → secured-storage rules

The room itself just needs a way to mark "this room has installation X" and
expose that to the consuming system. The installation systems themselves
each warrant their own design pass.

### Hierarchical stats consumed by systems

Specific consumers identified that will read this stats substrate:
- **Encounter generator** — uses `crime`, `order`, `traffic` to roll ambient
  encounters when characters move through a room
- **Check-difficulty modifier** — uses `lighting` (stealth/perception),
  `noise` (eavesdropping/quiet-action), `crime` (infiltration/streetwise) to
  modify DCs
- **Where-command coloring** — uses stats to flag "hot" rooms
- **Events bonuses** (when seeded) — uses `prestige`, `comfort`, `fashion` to
  modify event-related rolls and rewards
- **Weather system** (when built) — *writes* `temperature`, `humidity`,
  `exposure` modifiers at region level; consumers gate on `RoomProfile.is_outdoor`
- **Magic / resonance** (when seeded) — *both* writes (rituals contribute
  modifiers; sacred sites have overrides) and reads (spell potency modified
  by ambient magical stats)

Each of these is a follow-up integration as their consuming systems land.

## Roadmap implications

Updates to `docs/roadmap/rooms-and-estates.md`:
- Note the stats substrate as the foundational data layer for "room state" features
- Defer ownership / tenancy design to its own brainstorm (see "Out of scope" above)
- Mark installations as "each its own gameplay system" rather than treating them
  as a unified room-features list

A future `docs/roadmap/rooms.md` (called out in the 2026-05-06 brainstorm) can
absorb this stats layer plus the deferred items above into a coherent
rooms-as-system roadmap.

## Test plan

- **Cascade rule:**
  - Override at room level wins over override at any area level
  - Most-specific area override wins among multiple ancestor overrides
  - Override anywhere in the chain hides all modifiers
  - With no overrides, all modifiers across the chain sum + default + clamp
  - Empty chain (no rows) returns the per-stat default, clamped
- **Decay/growth math:**
  - `change_per_day=0` → constant value
  - `change_per_day < 0` with positive value → linear decay; returns 0 once
    crossed zero
  - `change_per_day > 0` with negative value → linear growth toward 0; returns
    0 once crossed
  - `change_per_day > 0` with positive value → unbounded growth; final clamp
    happens at the cascade resolver
- **Constraints:**
  - Cannot create two `LocationStatOverride` rows for the same `(area, stat_key)`
    (DB-level partial unique)
  - Cannot create two `LocationStatOverride` rows for the same `(room_profile, stat_key)`
  - DiscriminatorMixin rejects rows where both `area` and `room_profile` are set,
    or neither is set
- **Defaults / fallbacks:**
  - Room with no `RoomProfile` → cascades from area-less; returns default
  - Room with `RoomProfile` but `area=None` → returns default
- **`is_outdoor` field:**
  - Default is `False`
  - Migration applies cleanly to existing `RoomProfile` rows

## Cross-cutting notes

- All models inherit `SharedMemoryModel`. Trust the identity map — no
  `resolve_*` helpers, no `batch_fetch_*` helpers, no `Prefetch(to_attr=...)`
  for per-request data on the parent models.
- Service uses absolute imports, type annotations on all functions, no
  relative imports.
- TextChoices in `constants.py`, not nested classes inside models.
- Help text on every key field surfaces the Override-vs-Modifier discipline
  in admin so staff don't conflate the two.
- `world/locations/CLAUDE.md` captures the authoring rules for future
  contributors.
