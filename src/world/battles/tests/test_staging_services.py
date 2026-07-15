"""Tests for GM battle-staging services (#2010).

Covers: stage_battle, instantiate_battle_blueprint, spawn_units_from_template.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia import create_object

from world.battles.constants import (
    BattleSideRole,
    FortificationKind,
    TerrainType,
    UnitQuality,
)
from world.battles.exceptions import BattleStagingError
from world.battles.factories import (
    BattleFactory,
    BattleMapBlueprintFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
    BattleUnitTemplateCapabilityFactory,
    BattleUnitTemplateFactory,
    BattleVehicleFactory,
    BlueprintBattlePlaceFactory,
    BlueprintFortificationFactory,
)
from world.battles.models import BattlePlace
from world.battles.staging import (
    MAX_TEMPLATE_SPAWN,
    instantiate_battle_blueprint,
    spawn_units_from_template,
    stage_battle,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import RiskLevel
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import PropertyFactory
from world.scenes.constants import RoundStatus


class StageBattleTests(TestCase):
    def test_creates_battle_with_two_sides(self) -> None:
        battle = stage_battle(name="Siege of Ashwatch")

        self.assertEqual(battle.name, "Siege of Ashwatch")
        self.assertEqual(battle.sides.count(), 2)
        self.assertTrue(battle.sides.filter(role=BattleSideRole.ATTACKER).exists())
        self.assertTrue(battle.sides.filter(role=BattleSideRole.DEFENDER).exists())
        self.assertEqual(battle.places.count(), 0)

    def test_sets_risk_level(self) -> None:
        battle = stage_battle(name="Risky Siege", risk_level=RiskLevel.LETHAL)
        self.assertEqual(battle.risk_level, RiskLevel.LETHAL)

    def test_sets_region_after_creation(self) -> None:
        from world.areas.factories import AreaFactory

        area = AreaFactory()
        battle = stage_battle(name="Regional Siege", region=area)
        self.assertEqual(battle.region_id, area.pk)

    def test_defaults_campaign_story_and_region_to_none(self) -> None:
        battle = stage_battle(name="Standalone Siege")
        self.assertIsNone(battle.campaign_story)
        self.assertIsNone(battle.region)

    def test_stages_blueprint_places(self) -> None:
        blueprint = BattleMapBlueprintFactory()
        BlueprintBattlePlaceFactory(blueprint=blueprint, name="North Wall")
        BlueprintBattlePlaceFactory(blueprint=blueprint, name="South Gate")

        battle = stage_battle(name="Blueprinted Siege", blueprint=blueprint)

        self.assertEqual(battle.places.count(), 2)
        self.assertTrue(battle.places.filter(name="North Wall").exists())
        self.assertTrue(battle.places.filter(name="South Gate").exists())

    def test_binds_scene_location_when_given(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="Staging Room", nohome=True)

        battle = stage_battle(name="Located Siege", location=room)

        battle.scene.refresh_from_db()
        self.assertEqual(battle.scene.location, room)

    def test_leaves_scene_location_none_by_default(self) -> None:
        battle = stage_battle(name="Locationless Siege")

        battle.scene.refresh_from_db()
        self.assertIsNone(battle.scene.location)


class InstantiateBattleBlueprintTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.attacker = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.blueprint = BattleMapBlueprintFactory()
        self.bp_place = BlueprintBattlePlaceFactory(
            blueprint=self.blueprint,
            name="The Main Gates",
            terrain_type=TerrainType.FORTIFIED,
            movement_cost=2,
            x=Decimal("3.5"),
            y=Decimal("-1.25"),
            footprint_radius=Decimal(4),
        )

    def test_clones_places_with_geometry(self) -> None:
        places = instantiate_battle_blueprint(self.blueprint, self.battle)

        self.assertEqual(len(places), 1)
        place = places[0]
        self.assertEqual(place.battle, self.battle)
        self.assertEqual(place.name, "The Main Gates")
        self.assertEqual(place.terrain_type, TerrainType.FORTIFIED)
        self.assertEqual(place.movement_cost, 2)
        self.assertEqual(place.x, Decimal("3.5"))
        self.assertEqual(place.y, Decimal("-1.25"))
        self.assertEqual(place.footprint_radius, Decimal(4))

    def test_binds_fortification_to_side_role(self) -> None:
        BlueprintFortificationFactory(
            blueprint_place=self.bp_place,
            kind=FortificationKind.GATE,
            max_integrity=250,
            defending_side_role=BattleSideRole.DEFENDER,
        )

        places = instantiate_battle_blueprint(self.blueprint, self.battle)

        fort = places[0].fortifications.get()
        self.assertEqual(fort.defending_side, self.defender)
        self.assertEqual(fort.kind, FortificationKind.GATE)
        self.assertEqual(fort.max_integrity, 250)
        self.assertEqual(fort.integrity, 250)

    def test_raises_when_side_role_missing(self) -> None:
        no_defender_battle = BattleFactory()
        BattleSideFactory(battle=no_defender_battle, role=BattleSideRole.ATTACKER)
        BlueprintFortificationFactory(
            blueprint_place=self.bp_place, defending_side_role=BattleSideRole.DEFENDER
        )

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, no_defender_battle)

    def test_refuses_non_empty_without_replace(self) -> None:
        instantiate_battle_blueprint(self.blueprint, self.battle)

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, self.battle)

    def test_replace_tears_down_and_restages(self) -> None:
        instantiate_battle_blueprint(self.blueprint, self.battle)
        original_place_id = self.battle.places.get().pk

        BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="East Bastion")
        places = instantiate_battle_blueprint(self.blueprint, self.battle, replace=True)

        self.assertEqual(len(places), 2)
        self.assertFalse(BattlePlace.objects.filter(pk=original_place_id).exists())

    def test_replace_refused_after_round_exists(self) -> None:
        instantiate_battle_blueprint(self.blueprint, self.battle)
        BattleRoundFactory(battle=self.battle, round_number=1, status=RoundStatus.DECLARING)

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, self.battle, replace=True)

    def test_replace_refused_when_unit_stationed(self) -> None:
        places = instantiate_battle_blueprint(self.blueprint, self.battle)
        BattleUnitFactory(battle=self.battle, side=self.attacker, place=places[0])

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, self.battle, replace=True)

    def test_replace_refused_when_participant_stationed(self) -> None:
        places = instantiate_battle_blueprint(self.blueprint, self.battle)
        sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker, character_sheet=sheet, place=places[0]
        )

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, self.battle, replace=True)

    def test_replace_refused_when_vehicle_stationed(self) -> None:
        """A vehicle boarded onto a place blocks replace even with no units/
        participants stationed anywhere -- ``BattleVehicle.place`` is CASCADE
        (and the vehicle's own unit never has a ``place`` of its own, #1714), so
        tearing down the place would silently delete the vehicle too (#2010 review).
        """
        places = instantiate_battle_blueprint(self.blueprint, self.battle)
        vehicle_unit = BattleUnitFactory(battle=self.battle, side=self.attacker, place=None)
        BattleVehicleFactory(unit=vehicle_unit, place=places[0])

        with self.assertRaises(BattleStagingError):
            instantiate_battle_blueprint(self.blueprint, self.battle, replace=True)


class SpawnUnitsFromTemplateTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.flying = PropertyFactory(name="flying")
        self.flight_cap = CapabilityTypeFactory(name="flight")
        self.template = BattleUnitTemplateFactory(
            name="Wyvern Rider",
            descriptor="mounted wyvern cavalry",
            quality=UnitQuality.ELITE,
            strength=120,
            morale=80,
            individual_count=5,
        )
        self.template.properties.add(self.flying)
        BattleUnitTemplateCapabilityFactory(
            template=self.template, capability=self.flight_cap, value=30
        )

    def test_copies_stat_block(self) -> None:
        units = spawn_units_from_template(self.template, battle=self.battle, side=self.side)

        self.assertEqual(len(units), 1)
        unit = units[0]
        self.assertEqual(unit.name, "Wyvern Rider 1")
        self.assertEqual(unit.descriptor, "mounted wyvern cavalry")
        self.assertEqual(unit.quality, UnitQuality.ELITE)
        self.assertEqual(unit.strength, 120)
        self.assertEqual(unit.morale, 80)
        self.assertEqual(unit.individual_count, 5)
        self.assertTrue(unit.has_property(self.flying))
        self.assertEqual(unit.effective_capability(self.flight_cap), 30)

    def test_copies_capability_rows_exactly(self) -> None:
        units = spawn_units_from_template(self.template, battle=self.battle, side=self.side)
        unit = units[0]

        template_values = {
            (row.capability_id, row.value) for row in self.template.capability_values.all()
        }
        unit_values = {
            (row.capability_id, row.value) for row in unit.military_unit.capability_values.all()
        }
        self.assertEqual(template_values, unit_values)

    def test_batches_and_numbers_continuing_past_existing(self) -> None:
        spawn_units_from_template(self.template, battle=self.battle, side=self.side, count=2)

        more_units = spawn_units_from_template(
            self.template, battle=self.battle, side=self.side, count=3
        )

        names = sorted(u.name for u in more_units)
        self.assertEqual(names, ["Wyvern Rider 3", "Wyvern Rider 4", "Wyvern Rider 5"])

    def test_count_clamped_to_max(self) -> None:
        units = spawn_units_from_template(
            self.template, battle=self.battle, side=self.side, count=MAX_TEMPLATE_SPAWN + 10
        )
        self.assertEqual(len(units), MAX_TEMPLATE_SPAWN)

    def test_count_clamped_to_minimum_one(self) -> None:
        units = spawn_units_from_template(
            self.template, battle=self.battle, side=self.side, count=0
        )
        self.assertEqual(len(units), 1)

    def test_spawns_at_place(self) -> None:
        units = spawn_units_from_template(
            self.template, battle=self.battle, side=self.side, place=self.place
        )
        self.assertEqual(units[0].place, self.place)

    def test_bonus_units_spawned_for_covenant(self) -> None:
        """War-funding bonus_units spawns extra units from the same template (#2381)."""
        from world.battles.models import (
            WarFundingDetails,
            WarFundingTierBonus,
            WarFundingTierThreshold,
        )
        from world.battles.war_funding_services import complete_war_funding
        from world.covenants.factories import CovenantFactory
        from world.traits.factories import CheckOutcomeFactory

        covenant = CovenantFactory()
        side = BattleSideFactory(
            battle=self.battle, covenant=covenant, role=BattleSideRole.DEFENDER
        )

        # Create a completed war-funding project with bonus_units=2.
        from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
        from world.projects.factories import ProjectFactory

        project = ProjectFactory(
            kind=ProjectKind.WAR_FUNDING,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.COMPLETED,
        )
        details = WarFundingDetails.objects.create(project=project, covenant=covenant)
        critical = CheckOutcomeFactory(success_level=2)
        WarFundingTierThreshold.objects.create(
            details=details, outcome_tier=critical, min_progress=0
        )
        WarFundingTierBonus.objects.create(outcome_tier=critical, bonus_units=2)
        complete_war_funding(project, critical)

        units = spawn_units_from_template(self.template, battle=self.battle, side=side, count=1)
        self.assertEqual(len(units), 3)  # 1 requested + 2 bonus

    def test_bonus_units_clamped_to_max(self) -> None:
        """bonus_units + count is clamped to MAX_TEMPLATE_SPAWN (#2381)."""
        from world.battles.models import (
            WarFundingDetails,
            WarFundingTierBonus,
            WarFundingTierThreshold,
        )
        from world.battles.war_funding_services import complete_war_funding
        from world.covenants.factories import CovenantFactory
        from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
        from world.projects.factories import ProjectFactory
        from world.traits.factories import CheckOutcomeFactory

        covenant = CovenantFactory()
        side = BattleSideFactory(
            battle=self.battle, covenant=covenant, role=BattleSideRole.DEFENDER
        )

        project = ProjectFactory(
            kind=ProjectKind.WAR_FUNDING,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.COMPLETED,
        )
        details = WarFundingDetails.objects.create(project=project, covenant=covenant)
        critical = CheckOutcomeFactory(success_level=2)
        WarFundingTierThreshold.objects.create(
            details=details, outcome_tier=critical, min_progress=0
        )
        WarFundingTierBonus.objects.create(outcome_tier=critical, bonus_units=10)
        complete_war_funding(project, critical)

        units = spawn_units_from_template(
            self.template, battle=self.battle, side=side, count=MAX_TEMPLATE_SPAWN - 5
        )
        self.assertEqual(len(units), MAX_TEMPLATE_SPAWN)

    def test_no_bonus_units_without_covenant(self) -> None:
        """No bonus units when the side has no covenant (#2381)."""
        units = spawn_units_from_template(
            self.template, battle=self.battle, side=self.side, count=2
        )
        self.assertEqual(len(units), 2)
