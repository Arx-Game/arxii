"""FactoryBoy factories for the battles system tests."""

from __future__ import annotations

import factory
import factory.django as factory_django

from world.battles.constants import (
    DEFAULT_MORALE,
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionKind,
    BattleActionScope,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleMapBlueprint,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
    BattleUnitTemplate,
    BattleUnitTemplateCapability,
    BattleVehicle,
    BlueprintBattlePlace,
    BlueprintFortification,
    Fortification,
    WeatherTypeCapabilityChallenge,
    WeatherTypePropertyEffect,
)
from world.magic.factories import TechniqueFactory
from world.scenes.constants import RoundStatus


class BattleFactory(factory_django.DjangoModelFactory):
    """Creates a Battle; the backing Scene is auto-created by Battle.save()."""

    class Meta:
        model = Battle

    name = factory.Sequence(lambda n: f"Battle {n}")
    # Do NOT pass scene — save() auto-creates it.


class BattleSideFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleSide

    battle = factory.SubFactory(BattleFactory)
    role = BattleSideRole.ATTACKER
    victory_threshold = DEFAULT_VICTORY_THRESHOLD
    covenant = None


class BattlePlaceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattlePlace

    battle = factory.SubFactory(BattleFactory)
    name = factory.Sequence(lambda n: f"Place {n}")


class FortificationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Fortification

    place = factory.SubFactory(BattlePlaceFactory)
    defending_side = factory.SubFactory(
        BattleSideFactory, battle=factory.SelfAttribute("..place.battle")
    )
    building = None
    kind = FortificationKind.WALL
    integrity = 100
    max_integrity = 100
    breached = False


class BattleUnitFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleUnit

    battle = factory.SubFactory(BattleFactory)
    side = factory.SubFactory(BattleSideFactory, battle=factory.SelfAttribute("..battle"))
    name = factory.Sequence(lambda n: f"Unit {n}")
    descriptor = "generic"
    strength = 100
    status = BattleUnitStatus.ACTIVE


class BattleVehicleFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleVehicle

    unit = factory.SubFactory(BattleUnitFactory)
    place = factory.SubFactory(BattlePlaceFactory, battle=factory.SelfAttribute("..unit.battle"))
    vehicle_kind = VehicleKind.SHIP
    is_structural = True


class BattleMapBlueprintFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleMapBlueprint
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Blueprint {n}")
    description = ""
    is_active = True


class BlueprintBattlePlaceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BlueprintBattlePlace

    blueprint = factory.SubFactory(BattleMapBlueprintFactory)
    name = factory.Sequence(lambda n: f"Blueprint Place {n}")
    terrain_type = TerrainType.OPEN


class BlueprintFortificationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BlueprintFortification

    blueprint_place = factory.SubFactory(BlueprintBattlePlaceFactory)
    kind = FortificationKind.WALL
    max_integrity = 100
    defending_side_role = BattleSideRole.DEFENDER


class BattleUnitTemplateFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleUnitTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Unit Template {n}")
    descriptor = "generic"
    quality = UnitQuality.TRAINED
    strength = 100
    morale = DEFAULT_MORALE
    is_active = True


class BattleUnitTemplateCapabilityFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleUnitTemplateCapability

    template = factory.SubFactory(BattleUnitTemplateFactory)
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    value = 1


class BattleRoundFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleRound

    battle = factory.SubFactory(BattleFactory)
    round_number = 1
    status = RoundStatus.BETWEEN_ROUNDS


class BattleParticipantFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleParticipant

    battle = factory.SubFactory(BattleFactory)
    side = factory.SubFactory(BattleSideFactory, battle=factory.SelfAttribute("..battle"))
    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    status = BattleParticipantStatus.ACTIVE


class BattleActionDeclarationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleActionDeclaration

    battle_round = factory.SubFactory(BattleRoundFactory)
    participant = factory.SubFactory(
        BattleParticipantFactory,
        battle=factory.SelfAttribute("..battle_round.battle"),
    )
    technique = factory.SubFactory(TechniqueFactory, action_template=None)
    action_kind = BattleActionKind.STRIKE
    scope = BattleActionScope.UNIT
    resolved = False
    success_level = 0
    target_fortification = None


class WeatherTypePropertyEffectFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = WeatherTypePropertyEffect

    weather_type = factory.SubFactory("world.weather.factories.WeatherTypeFactory")
    property = factory.SubFactory("world.mechanics.factories.PropertyFactory")
    modifier = 10


class WeatherTypeCapabilityChallengeFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = WeatherTypeCapabilityChallenge

    weather_type = factory.SubFactory("world.weather.factories.WeatherTypeFactory")
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    threshold = 1
    modifier = -10


_PAYLOAD_PARAM = "@payload"


def _build_champion_duel_outcome_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the outcome handler."""
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition
    from world.battles.duel_wiring import CHAMPION_DUEL_TRIGGER_NAME

    flow, _ = FlowDefinition.objects.get_or_create(name=CHAMPION_DUEL_TRIGGER_NAME)
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.battles.duel_wiring.apply_champion_duel_outcome",
            parameters={"payload": _PAYLOAD_PARAM},
        )
    return flow


class BattleDuelOutcomeTriggerDefinitionFactory(factory_django.DjangoModelFactory):
    """TriggerDefinition for the ENCOUNTER_COMPLETED -> Champion duel outcome consumer (#1710).

    Installed on duel-encounter rooms by ``install_champion_duel_trigger``;
    dispatches ENCOUNTER_COMPLETED to ``apply_champion_duel_outcome``, which
    routs/destroys the losing side's unit at the bound BattlePlace and credits
    the winner's side.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "encounter_completed_champion_duel_outcome"
    event_name = "encounter_completed"
    flow_definition = factory.LazyFunction(_build_champion_duel_outcome_flow)
    priority = 40
    base_filter_condition = None


def ensure_battle_command_modifier_target():
    """Idempotently seed the "Battle Command" ModifierTarget (#1711).

    category="stat" is already in EQUIPMENT_RELEVANT_CATEGORIES
    (world/mechanics/constants.py), so authored covenant-role/facet/mantle
    bonuses against this target flow through the existing
    get_modifier_total/equipment_walk_total seam with no new plumbing —
    only the target row itself is new. Mirrors world/vitals/factories.py's
    ensure_surrounded_content idempotent-seed pattern.
    """
    from world.battles.constants import BATTLE_COMMAND_TARGET_NAME
    from world.mechanics.constants import STAT_CATEGORY_NAME
    from world.mechanics.models import ModifierCategory, ModifierTarget

    stat_category, _ = ModifierCategory.objects.get_or_create(
        name=STAT_CATEGORY_NAME,
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )
    target, _ = ModifierTarget.objects.get_or_create(
        category=stat_category,
        name=BATTLE_COMMAND_TARGET_NAME,
        defaults={
            "description": "Leadership bonus a commander grants to participants "
            "fighting alongside their commanded unit (#1711).",
            "is_active": True,
        },
    )
    return target
