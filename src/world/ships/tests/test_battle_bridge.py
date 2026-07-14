"""Tests for materialize_ship_as_battle_vehicle (#1832 Task 6)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.battles.constants import (
    BASE_INTEGRITY,
    FORTIFICATION_LEVEL_INTEGRITY_BONUS,
    FortificationKind,
)
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.models import Fortification
from world.conditions.models import CapabilityType
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode
from world.military.models import MilitaryUnitCapability
from world.room_features.factories import RoomFeatureInstanceFactory
from world.ships.battle_bridge import materialize_ship_as_battle_vehicle
from world.ships.constants import DAMAGED_HULL_DISCOUNT, SPEED_CAPABILITY_NAME
from world.ships.factories import ShipDetailsFactory
from world.ships.models import ShipDeployment


def _sanctum_for_ship(ship) -> SanctumDetails:
    room_profile = RoomProfileFactory(area=ship.building.area)
    feature_instance = RoomFeatureInstanceFactory(room_profile=room_profile)
    return SanctumDetails.objects.create(
        feature_instance=feature_instance,
        resonance_type=ResonanceFactory(),
        owner_mode=SanctumOwnerMode.PERSONAL,
    )


class MaterializeShipAsBattleVehicleTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)

    def test_hull_integrity_snapshots_fortification_level(self) -> None:
        ship = ShipDetailsFactory()
        ship.building.fortification_level = 2
        ship.building.save()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        expected = BASE_INTEGRITY[FortificationKind.HULL] + 2 * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        self.assertEqual(fortification.max_integrity, expected)
        self.assertEqual(fortification.integrity, expected)

    def test_needs_repair_lowers_hull_integrity(self) -> None:
        ship = ShipDetailsFactory(needs_repair=True)
        ship.building.fortification_level = 2
        ship.building.save()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        base = BASE_INTEGRITY[FortificationKind.HULL] + 2 * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        expected = max(1, base - DAMAGED_HULL_DISCOUNT * FORTIFICATION_LEVEL_INTEGRITY_BONUS)
        self.assertEqual(fortification.max_integrity, expected)
        self.assertEqual(fortification.integrity, expected)

    def test_speed_capability_created_and_matches_effective_handling(self) -> None:
        ship = ShipDetailsFactory()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        speed = CapabilityType.objects.get(name=SPEED_CAPABILITY_NAME)
        self.assertEqual(vehicle.unit.effective_capability(speed), ship.effective_handling())

    def test_strength_matches_effective_armament(self) -> None:
        ship = ShipDetailsFactory()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        vehicle.unit.refresh_from_db()
        self.assertEqual(vehicle.unit.strength, ship.effective_armament())

    def test_ship_deployment_links_ship_and_vehicle(self) -> None:
        ship = ShipDetailsFactory()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        deployment = ShipDeployment.objects.get(ship=ship, battle=self.battle)
        self.assertEqual(deployment.vehicle, vehicle)

    def test_level_3_sanctum_thread_adds_bonus_and_capability(self) -> None:
        ship = ShipDetailsFactory()
        ship.building.fortification_level = 1
        ship.building.save()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            resonance=resonance,
            level=3,
        )

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        vehicle.unit.refresh_from_db()
        # Hull: base + (fortification_level + bonus.hull) * per-level bonus.
        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        level = ship.building.fortification_level + 3
        expected_integrity = (
            BASE_INTEGRITY[FortificationKind.HULL] + level * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        )
        self.assertEqual(fortification.max_integrity, expected_integrity)

        # Handling and armament both get the sanctum bonus applied.
        speed = CapabilityType.objects.get(name=SPEED_CAPABILITY_NAME)
        self.assertEqual(vehicle.unit.effective_capability(speed), ship.effective_handling() + 3)
        self.assertEqual(vehicle.unit.strength, ship.effective_armament() + 3)

        # A level-3 capability row exists for the resonance.
        self.assertTrue(
            MilitaryUnitCapability.objects.filter(
                unit=vehicle.unit.military_unit,
                capability__name=f"sanctum_{resonance.name.lower()}",
            ).exists()
        )


class SiegeDeckBonusTests(TestCase):
    """A Siege Deck on the ship's deck room adds to effective armament (#675)."""

    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)

    def test_siege_deck_adds_armament_bonus(self) -> None:
        from world.room_features.seeds import ensure_siege_deck_kind

        ship = ShipDetailsFactory()
        kind = ensure_siege_deck_kind()
        room_profile = RoomProfileFactory(area=ship.building.area)
        RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind, level=2)

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        vehicle.unit.refresh_from_db()
        # effective_armament + (siege_deck.level * SIEGE_DECK_ARMAMENT_PER_LEVEL)
        from world.ships.constants import SIEGE_DECK_ARMAMENT_PER_LEVEL

        expected = ship.effective_armament() + 2 * SIEGE_DECK_ARMAMENT_PER_LEVEL
        self.assertEqual(vehicle.unit.strength, expected)

    def test_no_siege_deck_means_base_armament(self) -> None:
        ship = ShipDetailsFactory()

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        vehicle.unit.refresh_from_db()
        self.assertEqual(vehicle.unit.strength, ship.effective_armament())
