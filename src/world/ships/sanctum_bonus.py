"""Ship sanctum bonus + capability read (#1832 Task 5; catalog-driven since #2736).

A ship's persistent stat bonus and unlocked capabilities are derived from the
woven SANCTUM threads on the ship's sanctum room, if it has one. A ship has at
most one sanctum room for MVP.

**Both halves read the authored ``ThreadPullEffect`` catalog** — the same lookup
table the character-side thread handler reads, keyed
``(target_kind, resonance, tier, min_thread_level)``. ``TargetKind.SANCTUM`` rows at
tier 0 with ``effect_kind=VITAL_BONUS`` and a ``SHIP_*`` ``vital_target`` carry the
stat bonus; rows with ``effect_kind=CAPABILITY_GRANT`` carry the capability. Before
#2736 neither half was authored: the stat bonus was ``hull = handling = armament =
Σ thread levels`` (so every sanctified ship sailed identically) and the capability was
a ``CapabilityType`` named ``sanctum_<resonance>`` minted at battle time, at a flat
value nothing read. See ADR-0188.

A resonance with no authored row grants nothing, and that is not an error — the same
absent-row-means-inert rule the rest of the pull-effect catalog follows.
"""

from __future__ import annotations

from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget
from world.magic.models import SanctumDetails, Thread, ThreadPullEffect
from world.magic.services.capability_curve import (
    apply_capability_curve,
    get_capability_power_config,
)
from world.magic.services.threads import thread_level_multiplier
from world.ships.models import ShipDetails
from world.ships.types import ShipCapabilityGrant, ShipStatBonus

#: Which ``ShipStatBonus`` field each ship-flavoured ``VitalBonusTarget`` feeds.
_STAT_FOR_TARGET: dict[str, str] = {
    VitalBonusTarget.SHIP_HULL: "hull",
    VitalBonusTarget.SHIP_HANDLING: "handling",
    VitalBonusTarget.SHIP_ARMAMENT: "armament",
}


def _sanctum_for_ship(ship: ShipDetails) -> SanctumDetails | None:
    """Return the active ``SanctumDetails`` installed on one of the ship's rooms.

    Mirrors the filter style of ``sanctum_in_room``
    (``actions/definitions/sanctum.py``): the ship's rooms are the
    ``RoomProfile``s whose ``area`` matches the ship's backing ``Building``'s
    area. A ship has at most one sanctum room for MVP.
    """
    return (
        SanctumDetails.objects.filter(
            feature_instance__room_profile__area=ship.building.area,
            feature_instance__dissolved_at__isnull=True,
        )
        # feature_instance.level is the power figure the capability curve reads;
        # joining it here keeps that a free attribute access, not a second query.
        .select_related("feature_instance")
        .first()
    )


def _best_level_by_resonance(sanctum: SanctumDetails) -> dict[int, int]:
    """Return resonance pk -> highest active woven thread level on ``sanctum``.

    One query. Several threads may share a resonance (a personal thread and a
    helper's, say); the deepest one supplies the multiplier, and the grant applies
    once — the same fold ``passive_vital_bonuses`` uses for two threads sharing a
    ``(kind, resonance)`` key (#1009).
    """
    best: dict[int, int] = {}
    for resonance_id, level in Thread.objects.filter(
        target_sanctum_details=sanctum,
        retired_at__isnull=True,
    ).values_list("resonance_id", "level"):
        best[resonance_id] = max(best.get(resonance_id, 0), level)
    return best


def _sanctum_rows(
    resonance_ids: list[int], effect_kind: str, *, with_capability: bool = False
) -> list[ThreadPullEffect]:
    """Fetch every authored tier-0 SANCTUM row of one effect kind, in ONE query.

    Batched across all the ship's resonances rather than queried per resonance: the
    per-grant N+1 is the shape #2708 review caught twice in
    ``world/magic/handlers.py`` (see its ``_passive_capability_grants_cache``
    docstring), and this is the same loop in a different app.

    ``with_capability`` joins the granted ``CapabilityType``. Only the
    CAPABILITY_GRANT caller needs it; the VITAL_BONUS caller would be paying for a
    join onto a column its rows leave null.
    """
    rows = ThreadPullEffect.objects.filter(
        target_kind=TargetKind.SANCTUM,
        resonance_id__in=resonance_ids,
        tier=0,
        effect_kind=effect_kind,
    )
    if with_capability:
        rows = rows.select_related("capability_grant")
    return list(rows)


def ship_sanctum_bonus(ship: ShipDetails) -> ShipStatBonus:
    """Sum the authored ship-stat rows for the sanctum's resonances, + Siege Deck.

    Each woven resonance contributes to whichever of hull / handling / armament its
    authored ``VITAL_BONUS`` row names, scaled by the deepest thread on that resonance
    (``thread_level_multiplier``, #1718) exactly as the character-side passive bonus
    scales. Contributions from different resonances **sum** — they are stat points from
    independent sources, not a capability magnitude, so there is no MAX fold here.

    The Siege Deck armament bonus (#675) is added on top, unchanged and independent of
    any sanctum. Returns ``ShipStatBonus()`` (all zeros) when the ship has no sanctum,
    no active woven threads, no authored rows, and no Siege Deck.
    """
    totals = {"hull": 0, "handling": 0, "armament": 0}

    sanctum = _sanctum_for_ship(ship)
    if sanctum is not None:
        level_by_resonance = _best_level_by_resonance(sanctum)
        if level_by_resonance:
            rows = _sanctum_rows(list(level_by_resonance), EffectKind.VITAL_BONUS)
            for row in rows:
                stat = _STAT_FOR_TARGET.get(row.vital_target)
                if stat is None or row.vital_bonus_amount is None:
                    # A character-vital row authored on a SANCTUM resonance is the
                    # weaver's business, not the ship's; skip rather than mis-apply.
                    continue
                level = level_by_resonance[row.resonance_id]
                if row.min_thread_level > level:
                    continue
                totals[stat] += round(row.vital_bonus_amount * thread_level_multiplier(level))

    totals["armament"] += _siege_deck_armament_bonus(ship)

    return ShipStatBonus(**totals)


def _siege_deck_armament_bonus(ship: ShipDetails) -> int:
    """Total armament bonus from active Siege Decks on the ship's rooms (#675).

    A ship's rooms are the ``RoomProfile``s whose ``area`` matches the ship's
    backing ``Building``'s area. There can be at most one feature per room
    (RoomFeatureInstance is OneToOne), but multiple rooms in the area could
    each carry a Siege Deck — sum them all.
    """
    from world.room_features.constants import (  # noqa: PLC0415
        RoomFeatureServiceStrategy,
    )
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415
    from world.ships.constants import SIEGE_DECK_ARMAMENT_PER_LEVEL  # noqa: PLC0415

    instances = RoomFeatureInstance.objects.filter(
        room_profile__area=ship.building.area,
        feature_kind__service_strategy=RoomFeatureServiceStrategy.SIEGE_DECK,
        dissolved_at__isnull=True,
    )
    return sum(inst.level * SIEGE_DECK_ARMAMENT_PER_LEVEL for inst in instances)


def ship_sanctum_capability_grants(ship: ShipDetails) -> list[ShipCapabilityGrant]:
    """Return the capabilities the ship's sanctum confers, already curved to a value.

    For each woven resonance, the authored ``CAPABILITY_GRANT`` row with the **highest
    qualifying** ``min_thread_level`` wins — so a catalog may author a deeper unlock
    (``min_thread_level=6``) that supersedes the shallow one without the code knowing
    the numbers. There is deliberately **no hardcoded level-3 floor** any more: the
    authored ``min_thread_level`` is the gate, which is the whole point of moving this
    onto the catalog. Content authors 3 for the first unlock.

    **Magnitude.** ``apply_capability_curve(base, power=…, sensitivity=…)`` is
    geometric in ``power`` and inert when ``power <= 0`` — so ``sensitivity`` alone
    does nothing, and a ship needs a power figure of its own. It uses the **sanctum's
    installed level**: that is the shrine's own strength (it is already the basis of
    the anchor cap, ``feature_instance.level x 10``) and it belongs to the vessel
    rather than to whichever character happened to consecrate it. Thread depth enters
    as ``sensitivity``, exactly as on the character side, so a deeper thread in a
    stronger sanctum grants more on both axes.

    ``CapabilityPowerConfig`` is fetched **once** for the whole call, never per grant.

    Two resonances granting the same capability fold via MAX, not sum — ADR-0034
    individuation, matching ``_passive_capability_grants_cache``.
    """
    sanctum = _sanctum_for_ship(ship)
    if sanctum is None:
        return []

    level_by_resonance = _best_level_by_resonance(sanctum)
    if not level_by_resonance:
        return []

    rows = _sanctum_rows(
        list(level_by_resonance), EffectKind.CAPABILITY_GRANT, with_capability=True
    )
    if not rows:
        return []

    config = get_capability_power_config()  # fetched once for the whole build
    power = sanctum.feature_instance.level

    # Highest qualifying min_thread_level wins per resonance.
    best_row: dict[int, ThreadPullEffect] = {}
    for row in rows:
        if row.capability_grant_id is None:
            continue
        level = level_by_resonance[row.resonance_id]
        if row.min_thread_level > level:
            continue
        incumbent = best_row.get(row.resonance_id)
        if incumbent is None or row.min_thread_level > incumbent.min_thread_level:
            best_row[row.resonance_id] = row

    granted: dict[int, ShipCapabilityGrant] = {}
    for resonance_id, row in best_row.items():
        value = apply_capability_curve(
            row.capability_grant_value,
            power=power,
            sensitivity=thread_level_multiplier(level_by_resonance[resonance_id]),
            config=config,
        )
        incumbent = granted.get(row.capability_grant_id)
        if incumbent is None or value > incumbent.value:
            granted[row.capability_grant_id] = ShipCapabilityGrant(
                capability=row.capability_grant, value=value
            )

    return list(granted.values())
