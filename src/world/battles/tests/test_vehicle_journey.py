"""E2E journey: naval ship battle vehicle, from creation to sinking (#1714)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    BattleActionKind,
    BattleActionScope,
    BattleSideRole,
    FortificationKind,
    VehicleKind,
)
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.battles.models import BattleUnitCapability
from world.battles.resolution import resolve_battle_round
from world.battles.services import (
    begin_battle_round,
    create_battle_vehicle,
    declare_battle_action,
    places_overlap,
)
from world.conditions.factories import CapabilityTypeFactory, ensure_drowning_damage_type
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
from world.mechanics.factories import PropertyFactory
from world.vitals.factories import CharacterVitalsFactory


def _mock_check(success_level: int) -> MagicMock:
    """Mirrors test_siege.py's helper exactly."""
    result = MagicMock()
    result.success_level = success_level
    return result


class VehicleJourneyTests(TestCase):
    def test_ship_created_moved_boarded_and_sunk(self):
        battle = BattleFactory(round_limit=20)
        attacker_side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        defender_side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)

        attacker_ship = create_battle_vehicle(
            battle=battle,
            side=attacker_side,
            place_name="The Wave Cutter",
            vehicle_kind=VehicleKind.SHIP,
        )
        defender_ship = create_battle_vehicle(
            battle=battle,
            side=defender_side,
            place_name="The Iron Gull",
            vehicle_kind=VehicleKind.SHIP,
        )

        technique = TechniqueFactory(action_template=ActionTemplateFactory())

        captain = BattleParticipantFactory(
            battle=battle,
            side=attacker_side,
            place=attacker_ship.place,
        )
        attacker_ship.unit.commander = captain.character_sheet
        attacker_ship.unit.save(update_fields=["commander"])
        CharacterTechniqueFactory(character=captain.character_sheet, technique=technique)
        CharacterAnimaFactory(character=captain.character_sheet.character, current=30, maximum=30)

        gunner = BattleParticipantFactory(
            battle=battle,
            side=attacker_side,
            place=attacker_ship.place,
        )
        CharacterTechniqueFactory(character=gunner.character_sheet, technique=technique)
        CharacterAnimaFactory(character=gunner.character_sheet.character, current=30, maximum=30)

        non_swimmer = BattleParticipantFactory(
            battle=battle,
            side=defender_side,
            place=defender_ship.place,
        )
        CharacterVitalsFactory(
            character_sheet=non_swimmer.character_sheet, health=100, max_health=100
        )
        PropertyFactory(name="aquatic")

        defender_ship.place.x = Decimal(0)
        defender_ship.place.y = Decimal(0)
        defender_ship.place.footprint_radius = Decimal(5)
        defender_ship.place.save(update_fields=["x", "y", "footprint_radius"])
        attacker_ship.place.x = Decimal(50)
        attacker_ship.place.y = Decimal(0)
        attacker_ship.place.footprint_radius = Decimal(5)
        attacker_ship.place.save(update_fields=["x", "y", "footprint_radius"])

        self.assertFalse(places_overlap(attacker_ship.place, defender_ship.place))

        # 1. Close the gap: REPOSITION every round (bounded by whatever SPEED
        # capability the vehicle has — none set here, so distance stays 0 unless
        # a capability is granted; grant a generous SPEED so this converges fast).
        speed = CapabilityTypeFactory(name="speed")
        BattleUnitCapability.objects.create(unit=attacker_ship.unit, capability=speed, value=50)

        while not places_overlap(attacker_ship.place, defender_ship.place):
            battle_round = begin_battle_round(battle=battle)
            declare_battle_action(
                participant=captain,
                action_kind=BattleActionKind.REPOSITION,
                technique=technique,
                scope=BattleActionScope.PLACE,
                target_place=attacker_ship.place,
                reposition_dx=Decimal(-50),
                reposition_dy=Decimal(0),
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)
            attacker_ship.place.refresh_from_db()

        # 2. Ships now overlap — BREACH the defender's hull to 0.
        hull = defender_ship.place.fortifications.get(kind=FortificationKind.HULL)
        while not hull.breached:
            battle_round = begin_battle_round(battle=battle)
            declare_battle_action(
                participant=gunner,
                action_kind=BattleActionKind.BREACH,
                technique=technique,
                target_fortification=hull,
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)
            hull.refresh_from_db()

        self.assertTrue(hull.breached)

        # 3. Ejection consequence ran: non_swimmer's place is cleared and they
        # took real drowning damage; the aquatic Property exists (created above)
        # and the Drowning DamageType exists (created idempotently by ejection).
        non_swimmer.refresh_from_db()
        self.assertIsNone(non_swimmer.place)
        self.assertLess(non_swimmer.character_sheet.vitals.health, 100)
        self.assertEqual(ensure_drowning_damage_type().name, "Drowning")
