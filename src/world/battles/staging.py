"""GM battle-staging services (#2010).

Turns a JUNIOR-trust GM's catalog picks (``BattleMapBlueprint``,
``BattleUnitTemplate``) into a live ``Battle`` — a GM stages a battle rather
than inventing terrain/fortification layouts or unit stat blocks from
scratch. Built entirely on top of the setup services in
``world.battles.services`` (``create_battle``, ``add_side``, ``add_place``,
``add_unit``, ``create_fortification``); this module never writes to battle
models directly, mirroring services.py's own invariant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.battles.constants import BattleSideRole
from world.battles.exceptions import BattleStagingError
from world.battles.models import (
    Battle,
    BattleMapBlueprint,
    BattlePlace,
    BattleSide,
    BattleUnit,
    BattleUnitTemplate,
)
from world.battles.services import (
    add_place,
    add_side,
    add_unit,
    create_battle,
    create_fortification,
)
from world.combat.constants import RiskLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.models import Area
    from world.stories.models import Story

# Hard ceiling on a single spawn_units_from_template call — a GM batching a
# unit template onto the map, not an invitation to flood a battle with units.
MAX_TEMPLATE_SPAWN = 20


@transaction.atomic
def stage_battle(  # noqa: PLR0913 - each param is a distinct staging facet
    *,
    name: str,
    risk_level: str = RiskLevel.LOW,
    blueprint: BattleMapBlueprint | None = None,
    campaign_story: Story | None = None,
    region: Area | None = None,
    location: ObjectDB | None = None,
) -> Battle:
    """Create a Battle with both sides pre-added, optionally from a blueprint.

    Args:
        name: Human-readable name for the battle.
        risk_level: A ``RiskLevel`` value forwarded to ``create_battle``.
        blueprint: Optional ``BattleMapBlueprint`` whose places/fortifications
            are cloned onto the new battle via ``instantiate_battle_blueprint``.
        campaign_story: Optional parent Story this battle belongs to.
        region: Optional region anchor (``Battle.region``, #1715). ``create_battle``
            has no ``region`` kwarg, so this is set with a single extra save
            immediately after creation.
        location: Optional room to bind the battle's backing Scene to (#2010).
            ``Battle.save()`` creates that Scene with ``location=None`` (ADR-0081
            location-less battles), which leaves the battle unreachable by the
            room-scoped ``battle round``/``battle resolve``/``battle conclude``
            actions (``_active_battle_in_room``, ``actions/definitions/battles.py``).
            When given, binds ``battle.scene.location`` here so a GM who stages a
            battle from their current room can immediately run rounds on it.
            Defaults to None so direct service callers keep the location-less
            default.

    Returns:
        The newly created ``Battle``, with an ATTACKER and DEFENDER side (and,
        if ``blueprint`` was given, its cloned places/fortifications).
    """
    battle = create_battle(name=name, campaign_story=campaign_story, risk_level=risk_level)
    if region is not None:
        battle.region = region
        battle.save(update_fields=["region"])

    if location is not None:
        battle.scene.location = location
        battle.scene.save(update_fields=["location"])

    add_side(battle=battle, role=BattleSideRole.ATTACKER)
    add_side(battle=battle, role=BattleSideRole.DEFENDER)

    if blueprint is not None:
        instantiate_battle_blueprint(blueprint, battle)

    return battle


@transaction.atomic
def instantiate_battle_blueprint(
    blueprint: BattleMapBlueprint, battle: Battle, *, replace: bool = False
) -> list[BattlePlace]:
    """Clone *blueprint*'s places/fortifications onto *battle*.

    Args:
        blueprint: The catalog ``BattleMapBlueprint`` to instantiate.
        battle: The live ``Battle`` to stage places/fortifications onto.
        replace: When False (default) and ``battle`` already has places, raises
            rather than duplicating a staged map. When True, first tears down
            the battle's existing places (and their fortifications, via
            cascade) and re-stages from *blueprint* — but only when doing so
            is safe (see Raises).

    Raises:
        BattleStagingError: If ``battle`` already has places and ``replace``
            is False; if ``replace`` is True but the battle already has a
            BattleRound, or a unit/participant stationed at a place (tearing
            down would silently orphan live state); or if a
            ``BlueprintFortification.defending_side_role`` has no matching
            ``BattleSide`` on ``battle``.

    Returns:
        The newly created ``BattlePlace`` rows, in blueprint order.
    """
    if battle.places.exists():
        if not replace:
            msg = "This battle already has a staged map — pass replace=True to reset it."
            raise BattleStagingError(msg)
        _ensure_blueprint_replace_is_safe(battle)
        battle.places.all().delete()

    created_places: list[BattlePlace] = []
    for bp_place in blueprint.places.all():
        place = add_place(
            battle=battle,
            name=bp_place.name,
            terrain_type=bp_place.terrain_type,
            movement_cost=bp_place.movement_cost,
            x=bp_place.x,
            y=bp_place.y,
            footprint_radius=bp_place.footprint_radius,
        )
        for bp_fort in bp_place.fortifications.all():
            try:
                defending_side = battle.sides.get(role=bp_fort.defending_side_role)
            except BattleSide.DoesNotExist as exc:
                msg = (
                    f"This battle has no {bp_fort.defending_side_role} side to bind "
                    "that fortification's defending_side_role to."
                )
                raise BattleStagingError(msg) from exc
            create_fortification(
                place=place,
                defending_side=defending_side,
                kind=bp_fort.kind,
                max_integrity=bp_fort.max_integrity,
            )
        created_places.append(place)

    return created_places


def _ensure_blueprint_replace_is_safe(battle: Battle) -> None:
    """Raise BattleStagingError when tearing down ``battle``'s map would orphan
    live state (#2010) — a round has opened, a unit/participant is already
    stationed at one of its places, or a vehicle is boarded onto one of its
    places (``BattleVehicle.place`` is CASCADE, even when the vehicle's own
    unit has no boarded occupants yet — deleting the place would silently
    delete the vehicle too)."""
    if battle.rounds.exists():
        msg = "Cannot replace this battle's map — it already has at least one round."
        raise BattleStagingError(msg)
    if BattleUnit.objects.filter(battle=battle, place__isnull=False).exists():
        msg = "Cannot replace this battle's map — a unit is already stationed on it."
        raise BattleStagingError(msg)
    if battle.participants.filter(place__isnull=False).exists():
        msg = "Cannot replace this battle's map — a participant is already stationed on it."
        raise BattleStagingError(msg)
    if battle.places.filter(vehicle__isnull=False).exists():
        msg = "Cannot replace this battle's map — a vehicle is stationed on it."
        raise BattleStagingError(msg)


@transaction.atomic
def spawn_units_from_template(
    template: BattleUnitTemplate,
    *,
    battle: Battle,
    side: BattleSide,
    place: BattlePlace | None = None,
    count: int = 1,
) -> list[BattleUnit]:
    """Spawn one or more BattleUnits copying *template*'s authored stat block.

    Args:
        template: The catalog ``BattleUnitTemplate`` to spawn from.
        battle: The ``Battle`` to add the unit(s) to.
        side: The ``BattleSide`` the unit(s) belong to.
        place: Optional ``BattlePlace`` to station the unit(s) at.
        count: How many units to spawn, clamped to [1, MAX_TEMPLATE_SPAWN].
            Names continue numbering past any existing "<template.name> N"
            units already in this battle rather than restarting at 1.

    Returns:
        The newly created ``BattleUnit`` rows, in spawn order.
    """
    count = max(1, min(count, MAX_TEMPLATE_SPAWN))
    starting_number = _next_template_unit_number(template=template, battle=battle)
    properties = list(template.properties.all())
    capability_values = [(row.capability, row.value) for row in template.capability_values.all()]

    return [
        add_unit(
            battle=battle,
            side=side,
            name=f"{template.name} {starting_number + offset}",
            descriptor=template.descriptor,
            quality=template.quality,
            strength=template.strength,
            morale=template.morale,
            place=place,
            properties=properties,
            capability_values=capability_values,
            individual_count=template.individual_count,
        )
        for offset in range(1, count + 1)
    ]


def _next_template_unit_number(*, template: BattleUnitTemplate, battle: Battle) -> int:
    """Highest existing "<template.name> N" suffix among *battle*'s units, or 0.

    Lets a second spawn_units_from_template call continue numbering rather
    than colliding with units spawned from the same template earlier in the
    same battle (#2010).
    """
    prefix = f"{template.name} "
    highest = 0
    names = BattleUnit.objects.filter(
        battle=battle, military_unit__name__startswith=prefix
    ).values_list("military_unit__name", flat=True)
    for name in names:
        suffix = name[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest
