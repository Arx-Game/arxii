"""Game-content seeding for the battles app (#1710, #2010)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.battles.models import BattleMapBlueprint, BattleUnitTemplate


def seed_champion_duel_outcome_wiring() -> None:
    """Seed the ENCOUNTER_COMPLETED -> Champion-duel-outcome TriggerDefinition (#1710).

    Creates (get_or_create) the ``encounter_completed_champion_duel_outcome``
    FlowDefinition (one CALL_SERVICE_FUNCTION step -> apply_champion_duel_outcome)
    and its TriggerDefinition. Idempotent. The per-room Trigger is installed
    at duel-open time by ``open_champion_duel`` (via
    ``install_champion_duel_trigger``), not here.
    """
    from world.battles.duel_wiring import wire_champion_duel_trigger  # noqa: PLC0415

    wire_champion_duel_trigger()


def seed_place_encounter_outcome_wiring() -> None:
    """Seed the ENCOUNTER_COMPLETED -> place-encounter-outcome TriggerDefinition (#2008).

    Creates (get_or_create) the encounter_completed_place_encounter_outcome
    FlowDefinition (one CALL_SERVICE_FUNCTION step -> apply_place_encounter_outcome)
    and its TriggerDefinition. Idempotent. The per-room Trigger is installed at
    encounter-open time by ``open_place_encounter`` (via
    ``install_place_encounter_trigger``), not here.
    """
    from world.battles.place_encounter_wiring import wire_place_encounter_trigger  # noqa: PLC0415

    wire_place_encounter_trigger()


# ---------------------------------------------------------------------------
# Starter GM battle-staging catalog (#2010)
# ---------------------------------------------------------------------------
#
# Zero BattleMapBlueprint/BattleUnitTemplate rows existed anywhere pre-#2010 —
# the JUNIOR-trust staging actions/telnet grammar built by this feature
# (`battle create/stage/spawn/enlist/maps/units`) had nothing to browse or
# apply on a fresh DB. Seeds a minimal starter catalog via the app's own
# factories (natural-keyed on `name`, mirroring `world/seeds/game_content/
# missions.py`), never hand-authored `get_or_create` rows that would duplicate
# the factories' own uniqueness handling for no benefit.
#
# Shape (#2010): 2 BattleMapBlueprint rows, each with 3 named
# BlueprintBattlePlace fronts and one BlueprintFortification defending the
# chokepoint front — "River Crossing" (West Bank / The Ford / East Bank, a
# palisade-style wall fortification on East Bank) and "City Gates" (Gate
# Approach / The Gates, a wall fortification / Inner Court). Plus 3
# BattleUnitTemplate rows at distinct UnitQuality tiers ("Levy Spears",
# "Veteran Pikemen", "Raider Skirmishers"), each carrying at least one
# `mechanics.Property` tag and one `conditions.CapabilityType` magnitude —
# self-contained (get-or-create's its own Property/CapabilityType rows by
# name, same as `world/conditions/capability_content.py`) rather than
# depending on cluster-ordering against some other catalog seed, since no
# cluster seeds a generic Property/CapabilityType catalog today.


@dataclass
class BlueprintPlaceSpec:
    """One authored front within a starter BattleMapBlueprint (#2010)."""

    name: str
    terrain_type: str
    movement_cost: int = 1
    fortification_kind: str | None = None
    fortification_max_integrity: int = 100


@dataclass
class BattleStagingCatalogSeedResult:
    """Returned by seed_battle_staging_catalog()."""

    blueprints: list[BattleMapBlueprint]
    unit_templates: list[BattleUnitTemplate]


def _seed_blueprint(
    *, name: str, description: str, places: tuple[BlueprintPlaceSpec, ...]
) -> BattleMapBlueprint:
    """Get-or-create one starter BattleMapBlueprint + its place/fortification graph.

    ``BattleMapBlueprintFactory`` is ``django_get_or_create`` on ``name``, so
    the blueprint row itself is idempotent; the place/fortification graph is
    guarded separately (``blueprint.places.exists()``) since
    ``BlueprintBattlePlaceFactory`` has no such guard and would duplicate
    places (violating ``unique_blueprint_place_name``) on every re-run.
    """
    from world.battles.constants import BattleSideRole  # noqa: PLC0415
    from world.battles.factories import (  # noqa: PLC0415
        BattleMapBlueprintFactory,
        BlueprintBattlePlaceFactory,
        BlueprintFortificationFactory,
    )

    blueprint = BattleMapBlueprintFactory(name=name, description=description)
    if blueprint.places.exists():
        return blueprint  # already authored — idempotent no-op, preserves staff edits

    for spec in places:
        place = BlueprintBattlePlaceFactory(
            blueprint=blueprint,
            name=spec.name,
            terrain_type=spec.terrain_type,
            movement_cost=spec.movement_cost,
        )
        if spec.fortification_kind is not None:
            BlueprintFortificationFactory(
                blueprint_place=place,
                kind=spec.fortification_kind,
                max_integrity=spec.fortification_max_integrity,
                defending_side_role=BattleSideRole.DEFENDER,
            )

    return blueprint


def seed_battle_staging_catalog() -> BattleStagingCatalogSeedResult:
    """Seed the starter GM battle-staging catalog: 2 blueprints + 3 unit templates (#2010).

    Registered as part of the "battles" cluster in ``world.seeds.clusters`` —
    reachable from the Big Button. Idempotent throughout: re-running on a
    populated DB creates no new rows and never overwrites a staff edit.

    Returns:
        BattleStagingCatalogSeedResult with the 2 blueprints and 3 templates.
    """
    from world.battles.constants import FortificationKind, TerrainType  # noqa: PLC0415

    river_crossing = _seed_blueprint(
        name="River Crossing",
        description=(
            "A shallow ford splits an open floodplain — whoever holds the "
            "palisaded far bank commands the crossing."
        ),
        places=(
            BlueprintPlaceSpec(name="West Bank", terrain_type=TerrainType.OPEN),
            BlueprintPlaceSpec(name="The Ford", terrain_type=TerrainType.DIFFICULT),
            BlueprintPlaceSpec(
                name="East Bank",
                terrain_type=TerrainType.FORTIFIED,
                fortification_kind=FortificationKind.WALL,
            ),
        ),
    )
    city_gates = _seed_blueprint(
        name="City Gates",
        description=(
            "A walled city's main gate — an open approach, a fortified "
            "gatehouse, and the streets beyond once it falls."
        ),
        places=(
            BlueprintPlaceSpec(name="Gate Approach", terrain_type=TerrainType.OPEN),
            BlueprintPlaceSpec(
                name="The Gates",
                terrain_type=TerrainType.FORTIFIED,
                fortification_kind=FortificationKind.WALL,
            ),
            BlueprintPlaceSpec(name="Inner Court", terrain_type=TerrainType.URBAN),
        ),
    )

    unit_templates = _seed_starter_unit_templates()

    return BattleStagingCatalogSeedResult(
        blueprints=[river_crossing, city_gates], unit_templates=unit_templates
    )


@dataclass
class UnitTemplateSpec:
    """One authored starter BattleUnitTemplate (#2010)."""

    name: str
    descriptor: str
    quality: str
    strength: int
    property_name: str
    property_description: str
    capability_name: str
    capability_description: str
    capability_value: int


_UNIT_TEMPLATE_SPECS: tuple[UnitTemplateSpec, ...] = (
    UnitTemplateSpec(
        name="Levy Spears",
        descriptor="Hastily-mustered spear-armed conscripts",
        quality="levy",
        strength=60,
        property_name="spear-wall",
        property_description="Fights in a braced spear formation against a charge.",
        capability_name="melee_attack",
        capability_description="Close-quarters weapon combat proficiency.",
        capability_value=30,
    ),
    UnitTemplateSpec(
        name="Veteran Pikemen",
        descriptor="Drilled professional pike infantry",
        quality="veteran",
        strength=120,
        property_name="phalanx",
        property_description="Fights in a disciplined, deep pike formation.",
        capability_name="melee_attack",
        capability_description="Close-quarters weapon combat proficiency.",
        capability_value=75,
    ),
    UnitTemplateSpec(
        name="Raider Skirmishers",
        descriptor="Fast, lightly-armed irregular raiders",
        quality="militia",
        strength=80,
        property_name="mobile",
        property_description="Moves and disengages faster than a formed unit.",
        capability_name="ranged_attack",
        capability_description="Bow/thrown-weapon combat proficiency at range.",
        capability_value=50,
    ),
)


def _seed_starter_unit_templates() -> list[BattleUnitTemplate]:
    """Get-or-create the 3 starter BattleUnitTemplate rows + their property/capability values.

    ``BattleUnitTemplateFactory`` is ``django_get_or_create`` on ``name``, so
    the template row itself is idempotent (a staff edit to e.g. ``strength``
    on an existing row is never overwritten — the ``django_get_or_create``
    lookup-only-on-name behavior). The property/capability rows are
    idempotent on their own terms: the M2M ``properties.add`` is a natural
    no-op on repeat, and the capability magnitude is written via
    ``get_or_create`` (defaults only apply at creation, so a staff-edited
    magnitude survives a rerun too).
    """
    from world.battles.factories import BattleUnitTemplateFactory  # noqa: PLC0415
    from world.battles.models import BattleUnitTemplateCapability  # noqa: PLC0415
    from world.conditions.factories import CapabilityTypeFactory  # noqa: PLC0415
    from world.mechanics.factories import PropertyCategoryFactory, PropertyFactory  # noqa: PLC0415

    property_category = PropertyCategoryFactory(name="Battle Unit Traits")

    templates: list[BattleUnitTemplate] = []
    for spec in _UNIT_TEMPLATE_SPECS:
        template = BattleUnitTemplateFactory(
            name=spec.name,
            descriptor=spec.descriptor,
            quality=spec.quality,
            strength=spec.strength,
        )
        prop = PropertyFactory(
            name=spec.property_name,
            description=spec.property_description,
            category=property_category,
        )
        template.properties.add(prop)

        capability = CapabilityTypeFactory(
            name=spec.capability_name, description=spec.capability_description
        )
        BattleUnitTemplateCapability.objects.get_or_create(
            template=template,
            capability=capability,
            defaults={"value": spec.capability_value},
        )
        templates.append(template)

    return templates
