# Locations - Ambient Stats Cascade

Authored substrate for ambient room/area stats (crime, order, lighting, …).
Stats cascade through the area hierarchy and are read via a single service.

See `docs/plans/2026-05-09-location-stats-design.md` for the full design and
the rationale behind every choice.

## Models

- **`LocationStatOverride`** — absolute claim at a specific area or room.
  Most-specific override in the cascade chain wins, and any override
  anywhere in the chain causes ALL modifiers in that chain to be ignored.
  **Use rarely** — for warded sanctums, safehouses, magically stabilized
  chambers. The "this is the value, period" claim.
- **`LocationStatModifier`** — additive contribution. Stacks across the
  cascade chain. Carries `change_per_day` for read-time decay/growth.
  **The common authoring path** — including for what feels like
  "the permanent value at this level," which is just a modifier with
  `change_per_day=0`.

Both models inherit from `core.mixins.DiscriminatorMixin` and
`evennia.utils.idmapper.models.SharedMemoryModel`. The discriminator field
is `parent_type` (AREA or ROOM); only one of `area` / `room_profile` is set
per row.

## Cascade rule

For any `(room, stat_key)`:

1. Walk the closure chain from the room outward via `world.areas.AreaClosure`.
2. **If any level in the chain has authored an Override** → use the
   most-specific Override's value (clamped). All Modifiers ignored.
3. **Otherwise** → sum every Modifier's `current_value()` across the
   chain, plus `STAT_DEFAULTS[stat_key]`, clamp.

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
  to clean up later: `LocationStatModifier.objects.filter(source="rebellion_1234").delete()`.
- `change_per_day` is signed: negative decays toward zero, positive grows
  away from zero, zero is permanent. `current_value()` clamps to zero
  once a modifier crosses its original sign — eligible for cleanup but
  inert until then.

## Reading

Single service:

```python
from world.locations.services import effective_stat
from world.locations.constants import StatKey

crime_here = effective_stat(room, StatKey.CRIME)
```

That's it. No bulk reads, no convenience write helpers, no cleanup sweep
in v1 — they're added when consumers need them.

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
