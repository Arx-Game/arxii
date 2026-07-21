"""Tests for battle setup service functions (Task 5).

Covers: create_battle, add_side, add_place, add_unit, enlist_participant,
begin_battle_round, and the BattleError exception hierarchy.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia import create_object

from world.battles.constants import (
    BASE_INTEGRITY,
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    FORTIFICATION_LEVEL_INTEGRITY_BONUS,
    BattleOutcome,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.exceptions import (
    BattleConcludedError,
    NoCommandHierarchyError,
    NotAChampionError,
    PlaceAlreadyDuelingError,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.services import (
    create_battle_vehicle,
    create_fortification,
    eject_vehicle_occupants,
    open_champion_duel,
    open_siege_engine_encounter,
    places_overlap,
)
from world.buildings.factories import BuildingFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterType, RiskLevel
from world.combat.factories import ThreatPoolFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.mechanics.factories import PropertyFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory


class CreateBattleTests(TestCase):
    def test_create_battle_returns_battle_with_scene(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Test Battle")

        self.assertEqual(battle.name, "Test Battle")
        self.assertIsNotNone(battle.scene_id)
        self.assertEqual(battle.round_limit, DEFAULT_ROUND_LIMIT)
        self.assertEqual(battle.outcome, BattleOutcome.UNRESOLVED)
        self.assertFalse(battle.is_concluded)

    def test_create_battle_with_round_limit(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Capped Battle", round_limit=5)

        self.assertEqual(battle.round_limit, 5)

    def test_create_battle_without_campaign_story(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Standalone Battle")

        self.assertIsNone(battle.campaign_story)


class AddSideTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Side Test Battle")

    def test_add_attacker_side(self) -> None:
        from world.battles.services import add_side

        side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)

        self.assertEqual(side.battle, self.battle)
        self.assertEqual(side.role, BattleSideRole.ATTACKER)
        self.assertEqual(side.victory_threshold, DEFAULT_VICTORY_THRESHOLD)
        self.assertEqual(side.victory_points, 0)

    def test_add_defender_side_with_custom_threshold(self) -> None:
        from world.battles.services import add_side

        side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER, victory_threshold=150)

        self.assertEqual(side.role, BattleSideRole.DEFENDER)
        self.assertEqual(side.victory_threshold, 150)

    def test_two_sides_in_battle(self) -> None:
        from world.battles.services import add_side

        add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.assertEqual(self.battle.sides.count(), 2)

    def test_add_side_accepts_covenant(self) -> None:
        from world.battles.services import add_side, create_battle

        battle = create_battle(name="Siege of Thornwall")
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER, covenant=covenant)
        self.assertEqual(side.covenant_id, covenant.pk)


class AddPlaceTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Place Test Battle")

    def test_add_place(self) -> None:
        from world.battles.services import add_place

        place = add_place(battle=self.battle, name="The Main Gates")

        self.assertEqual(place.battle, self.battle)
        self.assertEqual(place.name, "The Main Gates")
        self.assertEqual(self.battle.places.count(), 1)


class AddUnitTests(TestCase):
    def setUp(self) -> None:
        from world.battles.services import add_place, add_side

        self.battle = BattleFactory(name="Unit Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.place = add_place(battle=self.battle, name="Front Gate")

    def test_add_unit_defaults(self) -> None:
        from world.battles.services import add_unit

        unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Cavalry",
            descriptor="cavalry",
        )

        self.assertEqual(unit.battle, self.battle)
        self.assertEqual(unit.side, self.attacker_side)
        self.assertEqual(unit.strength, 100)
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)
        self.assertIsNone(unit.place)

    def test_add_unit_at_place_with_custom_strength(self) -> None:
        from world.battles.services import add_unit

        unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Elite Guard",
            descriptor="guard",
            strength=80,
            place=self.place,
        )

        self.assertEqual(unit.strength, 80)
        self.assertEqual(unit.place, self.place)


class EnlistParticipantTests(TestCase):
    def setUp(self) -> None:
        from world.battles.services import add_side

        self.battle = BattleFactory(name="Enlist Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.sheet = CharacterSheetFactory()

    def test_enlist_participant(self) -> None:
        from world.battles.services import enlist_participant

        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.assertEqual(participant.battle, self.battle)
        self.assertEqual(participant.character_sheet, self.sheet)
        self.assertEqual(participant.side, self.side)
        self.assertIsNone(participant.place)

    def test_enlist_at_place(self) -> None:
        from world.battles.services import add_place, enlist_participant

        place = add_place(battle=self.battle, name="Outer Wall")
        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side, place=place
        )

        self.assertEqual(participant.place, place)


class BeginBattleRoundTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Round Test Battle")

    def test_begin_first_round(self) -> None:
        from world.battles.services import begin_battle_round

        battle_round = begin_battle_round(battle=self.battle)

        self.assertEqual(battle_round.battle, self.battle)
        self.assertEqual(battle_round.round_number, 1)
        self.assertEqual(battle_round.status, RoundStatus.DECLARING)

    def test_begin_second_round_increments_number(self) -> None:
        from world.battles.services import begin_battle_round

        first_round = begin_battle_round(battle=self.battle)
        self.assertEqual(first_round.round_number, 1)
        self.assertEqual(first_round.status, RoundStatus.DECLARING)

        second_round = begin_battle_round(battle=self.battle)

        self.assertEqual(second_round.round_number, 2)
        self.assertEqual(second_round.status, RoundStatus.DECLARING)

        # First round should now be COMPLETED
        first_round.refresh_from_db()
        self.assertEqual(first_round.status, RoundStatus.COMPLETED)

    def test_begin_round_raises_for_concluded_battle(self) -> None:
        from world.battles.services import begin_battle_round

        self.battle.outcome = BattleOutcome.DEFENDER_DECISIVE
        self.battle.save()

        with self.assertRaises(BattleConcludedError):
            begin_battle_round(battle=self.battle)

    def test_begin_round_after_resolve_increments_number(self) -> None:
        """After a round is externally set to COMPLETED (simulating resolution),
        begin_battle_round must still derive the correct next number from the
        last round in the DB — not default back to 1.
        """
        from world.battles.services import begin_battle_round

        first_round = begin_battle_round(battle=self.battle)
        self.assertEqual(first_round.round_number, 1)

        # Simulate external resolution: mark the round COMPLETED directly.
        first_round.status = RoundStatus.COMPLETED
        first_round.save(update_fields=["status"])

        second_round = begin_battle_round(battle=self.battle)

        self.assertEqual(second_round.round_number, 2)
        self.assertEqual(second_round.status, RoundStatus.DECLARING)

    def test_current_round_property(self) -> None:
        from world.battles.services import begin_battle_round

        self.assertIsNone(self.battle.current_round)

        round1 = begin_battle_round(battle=self.battle)
        self.battle.refresh_from_db()

        self.assertEqual(self.battle.current_round.pk, round1.pk)


class OpenChampionDuelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.battle = BattleFactory()
        cls.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        cls.side = BattleSideFactory(battle=cls.battle, covenant=cls.covenant)
        cls.place = BattlePlaceFactory(battle=cls.battle)
        cls.rank = CovenantRankFactory(covenant=cls.covenant)
        cls.champion_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            is_champion_role=True,
            slug="champion-svc-test",
        )
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Champion Duel Room", nohome=True)
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.sheet = CharacterSheetFactory()
        self.participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=self.sheet, place=self.place
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.champion_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

    def test_open_champion_duel_binds_place_to_new_encounter(self):
        enc = open_champion_duel(
            battle_place=self.place,
            challenger_participant=self.participant,
            opponent_kwargs={
                "name": "Warlord's Champion",
                "max_health": 300,
                "threat_pool": self.threat_pool,
            },
        )
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, enc.pk)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)
        # #2536 slice 3: Champion duels are the ONLY DUEL creation path that
        # stamps is_champion_duel=True (Situation.CHAMPION_DUEL scoping).
        self.assertIs(enc.is_champion_duel, True)

    def test_open_champion_duel_rejects_non_champion(self) -> None:
        other_sheet = CharacterSheetFactory()
        other_participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=other_sheet, place=self.place
        )
        with self.assertRaises(NotAChampionError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=other_participant,
                opponent_kwargs={
                    "name": "Warlord's Champion",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )

    def test_open_champion_duel_rejects_place_already_dueling(self) -> None:
        open_champion_duel(
            battle_place=self.place,
            challenger_participant=self.participant,
            opponent_kwargs={
                "name": "Warlord's Champion",
                "max_health": 300,
                "threat_pool": self.threat_pool,
            },
        )
        with self.assertRaises(PlaceAlreadyDuelingError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=self.participant,
                opponent_kwargs={
                    "name": "Second Boss",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )

    def test_open_champion_duel_rejects_side_with_no_covenant(self) -> None:
        no_covenant_side = BattleSideFactory(
            battle=self.battle, role=BattleSideRole.DEFENDER, covenant=None
        )
        other_sheet = CharacterSheetFactory()
        other_participant = BattleParticipantFactory(
            battle=self.battle,
            side=no_covenant_side,
            character_sheet=other_sheet,
            place=self.place,
        )
        with self.assertRaises(NoCommandHierarchyError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=other_participant,
                opponent_kwargs={
                    "name": "Warlord's Champion",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )


class OpenSiegeEngineEncounterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.battle = BattleFactory()
        cls.side = BattleSideFactory(battle=cls.battle)
        cls.place = BattlePlaceFactory(battle=cls.battle)
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        self.room = create_object(
            "typeclasses.rooms.Room", key="Siege Engine Skirmish Room", nohome=True
        )
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.sheet = CharacterSheetFactory()
        self.participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=self.sheet, place=self.place
        )

    def test_opens_encounter_and_binds_place(self) -> None:
        enc = open_siege_engine_encounter(
            battle_place=self.place,
            participant=self.participant,
            opponent_kwargs={
                "name": "Ram crew",
                "max_health": 30,
                "threat_pool": self.threat_pool,
            },
        )
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, enc.pk)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)
        # #2536 slice 3: siege-engine DUEL encounters share create_lethal_duel with
        # Champion duels but are NOT Champion duels — is_champion_duel stays False.
        self.assertIs(enc.is_champion_duel, False)

    def test_raises_if_place_already_dueling(self) -> None:
        open_siege_engine_encounter(
            battle_place=self.place,
            participant=self.participant,
            opponent_kwargs={
                "name": "Ram crew",
                "max_health": 30,
                "threat_pool": self.threat_pool,
            },
        )
        with self.assertRaises(PlaceAlreadyDuelingError):
            open_siege_engine_encounter(
                battle_place=self.place,
                participant=self.participant,
                opponent_kwargs={
                    "name": "Second ram crew",
                    "max_health": 30,
                    "threat_pool": self.threat_pool,
                },
            )


class OpenPlaceEncounterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.battle = BattleFactory()
        cls.place = BattlePlaceFactory(battle=cls.battle)

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Front Fight Room", nohome=True)
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

    def test_opens_bare_party_combat_encounter_and_binds_place(self) -> None:
        from world.battles.services import open_place_encounter

        enc = open_place_encounter(battle_place=self.place)

        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, enc.pk)
        self.assertEqual(enc.encounter_type, EncounterType.PARTY_COMBAT)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)
        self.assertEqual(enc.room_id, self.room.id)
        self.assertEqual(enc.participants.count(), 0)
        self.assertEqual(enc.opponents.count(), 0)

    def test_raises_when_place_already_bound(self) -> None:
        from world.battles.services import open_place_encounter

        open_place_encounter(battle_place=self.place)
        self.place.refresh_from_db()

        with self.assertRaises(PlaceAlreadyDuelingError):
            open_place_encounter(battle_place=self.place)


class AddUnitTaxonomyTests(TestCase):
    def test_add_unit_accepts_quality_commander(self) -> None:
        from world.battles.services import add_side, add_unit, create_battle

        battle = create_battle(name="Taxonomy Setup Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        commander = CharacterSheetFactory()

        unit = add_unit(
            battle=battle,
            side=side,
            name="Iron Cavalry",
            descriptor="armored knights",
            quality=UnitQuality.ELITE,
            commander=commander,
        )

        self.assertEqual(unit.descriptor, "armored knights")
        self.assertEqual(unit.quality, UnitQuality.ELITE)
        self.assertEqual(unit.commander, commander)

    def test_add_unit_accepts_properties_and_capability_values(self) -> None:
        from world.battles.services import add_side, add_unit, create_battle
        from world.conditions.factories import CapabilityTypeFactory
        from world.mechanics.factories import PropertyFactory

        battle = create_battle(name="Property Setup Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        flying = PropertyFactory(name="flying")
        flight_cap = CapabilityTypeFactory(name="flight")

        unit = add_unit(
            battle=battle,
            side=side,
            name="Wyvern Rider",
            properties=[flying],
            capability_values=[(flight_cap, 25)],
        )

        self.assertTrue(unit.has_property(flying))
        self.assertEqual(unit.effective_capability(flight_cap), 25)


class AddPlaceTerrainTests(TestCase):
    def test_add_place_accepts_terrain_and_movement_cost(self) -> None:
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Terrain Setup Test")
        place = add_place(
            battle=battle,
            name="The Marsh Crossing",
            terrain_type=TerrainType.FLOODED,
            movement_cost=3,
        )
        self.assertEqual(place.terrain_type, TerrainType.FLOODED)
        self.assertEqual(place.movement_cost, 3)

    def test_add_place_defaults(self) -> None:
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Terrain Default Test")
        place = add_place(battle=battle, name="Open Field")
        self.assertEqual(place.terrain_type, TerrainType.OPEN)
        self.assertEqual(place.movement_cost, 1)


class SetBattleSidePostureTests(TestCase):
    def test_sets_posture(self) -> None:
        from world.battles.services import add_side, create_battle, set_battle_side_posture

        battle = create_battle(name="Posture Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)

        updated = set_battle_side_posture(side=side, posture=BattlePosture.AGGRESSIVE)

        self.assertEqual(updated.posture, BattlePosture.AGGRESSIVE)
        side.refresh_from_db()
        self.assertEqual(side.posture, BattlePosture.AGGRESSIVE)


class AssignUnitCommanderTests(TestCase):
    def test_assigns_commander(self) -> None:
        from world.battles.services import add_side, add_unit, assign_unit_commander, create_battle

        battle = create_battle(name="Commander Assign Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        unit = add_unit(battle=battle, side=side, name="Levy Spears")
        commander = CharacterSheetFactory()

        updated = assign_unit_commander(unit=unit, commander=commander)

        self.assertEqual(updated.commander, commander)
        unit.refresh_from_db()
        self.assertEqual(unit.commander, commander)

    def test_clears_commander_with_none(self) -> None:
        from world.battles.services import add_side, add_unit, assign_unit_commander, create_battle

        battle = create_battle(name="Commander Clear Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        commander = CharacterSheetFactory()
        unit = add_unit(battle=battle, side=side, name="Levy Spears", commander=commander)

        assign_unit_commander(unit=unit, commander=None)

        unit.refresh_from_db()
        self.assertIsNone(unit.commander)


class CreateFortificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.battle = BattleFactory()
        cls.side = BattleSideFactory(battle=cls.battle)
        cls.place = BattlePlaceFactory(battle=cls.battle)

    def test_no_building_uses_base_integrity_only(self):
        fort = create_fortification(
            place=self.place, defending_side=self.side, kind=FortificationKind.WALL
        )
        self.assertEqual(fort.max_integrity, BASE_INTEGRITY[FortificationKind.WALL])
        self.assertEqual(fort.integrity, fort.max_integrity)

    def test_building_level_adds_flat_bonus(self):
        building = BuildingFactory(fortification_level=2)
        fort = create_fortification(
            place=self.place,
            defending_side=self.side,
            kind=FortificationKind.GATE,
            building=building,
        )
        expected = BASE_INTEGRITY[FortificationKind.GATE] + 2 * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        self.assertEqual(fort.max_integrity, expected)

    def test_zero_level_building_matches_no_building(self):
        building = BuildingFactory(fortification_level=0)
        fort = create_fortification(place=self.place, defending_side=self.side, building=building)
        self.assertEqual(fort.max_integrity, BASE_INTEGRITY[FortificationKind.WALL])


class CreateBattleVehicleTests(TestCase):
    def test_structural_vehicle_gets_hull_fortification(self):
        side = BattleSideFactory()
        vehicle = create_battle_vehicle(
            battle=side.battle,
            side=side,
            place_name="The Wave Cutter",
            vehicle_kind=VehicleKind.SHIP,
        )

        self.assertTrue(vehicle.is_structural)
        self.assertEqual(vehicle.unit.place, None)
        hull = vehicle.place.fortifications.get(kind=FortificationKind.HULL)
        self.assertEqual(hull.defending_side, side)
        self.assertEqual(hull.integrity, hull.max_integrity)

    def test_living_mount_gets_no_fortification(self):
        side = BattleSideFactory()
        vehicle = create_battle_vehicle(
            battle=side.battle,
            side=side,
            place_name="Skytalon",
            vehicle_kind=VehicleKind.DRAGON,
            is_structural=False,
        )

        self.assertFalse(vehicle.is_structural)
        self.assertEqual(vehicle.place.fortifications.count(), 0)


class PlacesOverlapTests(TestCase):
    def test_overlapping_footprints(self):
        battle = BattleFactory()
        a = BattlePlaceFactory(
            battle=battle, x=Decimal(0), y=Decimal(0), footprint_radius=Decimal(5)
        )
        b = BattlePlaceFactory(
            battle=battle, x=Decimal(6), y=Decimal(0), footprint_radius=Decimal(5)
        )

        self.assertTrue(places_overlap(a, b))

    def test_non_overlapping_footprints(self):
        battle = BattleFactory()
        a = BattlePlaceFactory(
            battle=battle, x=Decimal(0), y=Decimal(0), footprint_radius=Decimal(1)
        )
        b = BattlePlaceFactory(
            battle=battle, x=Decimal(100), y=Decimal(0), footprint_radius=Decimal(1)
        )

        self.assertFalse(places_overlap(a, b))


class EjectVehicleOccupantsTests(TestCase):
    def test_ejects_units_and_participants_and_clears_their_place(self):
        side = BattleSideFactory()
        vehicle = create_battle_vehicle(
            battle=side.battle,
            side=side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        passenger_unit = BattleUnitFactory(battle=side.battle, side=side, place=vehicle.place)
        passenger = BattleParticipantFactory(battle=side.battle, side=side, place=vehicle.place)
        CharacterVitalsFactory(
            character_sheet=passenger.character_sheet, health=100, max_health=100
        )

        eject_vehicle_occupants(vehicle=vehicle)

        passenger_unit.refresh_from_db()
        passenger.refresh_from_db()
        self.assertIsNone(passenger_unit.place)
        self.assertIsNone(passenger.place)
        self.assertLess(passenger.character_sheet.vitals.health, 100)

    def test_aquatic_unit_skips_hazard(self):
        side = BattleSideFactory()
        vehicle = create_battle_vehicle(
            battle=side.battle,
            side=side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        aquatic = PropertyFactory(name="aquatic")
        passenger_unit = BattleUnitFactory(battle=side.battle, side=side, place=vehicle.place)
        passenger_unit.military_unit.properties.add(aquatic)
        original_strength = passenger_unit.strength

        eject_vehicle_occupants(vehicle=vehicle)

        passenger_unit.refresh_from_db()
        self.assertEqual(passenger_unit.strength, original_strength)
