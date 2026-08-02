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
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.models import CapabilityType
from world.magic.constants import VitalBonusTarget
from world.magic.factories import ResonanceFactory
from world.military.models import MilitaryUnitCapability
from world.room_features.factories import RoomFeatureInstanceFactory
from world.ships.battle_bridge import materialize_ship_as_battle_vehicle
from world.ships.constants import DAMAGED_HULL_DISCOUNT, SPEED_CAPABILITY_NAME
from world.ships.factories import ShipDetailsFactory
from world.ships.models import ShipDeployment
from world.ships.tests._sanctum_catalog import (
    author_capability_row as _author_capability_row,
    author_stat_row as _author_stat_row,
    sanctum_for_ship as _sanctum_for_ship,
    weave as _weave,
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

    def test_sanctum_thread_applies_the_authored_stat_row_and_capability(self) -> None:
        """The bridge writes what the catalog resolved — hull bonus and capability (#2736)."""
        ship = ShipDetailsFactory()
        ship.building.fortification_level = 1
        ship.building.save()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        capability = CapabilityTypeFactory(name="traversal")
        _weave(sanctum, resonance, level=10)
        _author_stat_row(resonance, VitalBonusTarget.SHIP_HULL, 3)
        _author_capability_row(resonance, capability, base=2)

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        vehicle.unit.refresh_from_db()
        # Hull: base + (fortification_level + authored hull bonus) * per-level bonus.
        fortification = Fortification.objects.get(place=vehicle.place, kind=FortificationKind.HULL)
        level = ship.building.fortification_level + 3
        expected_integrity = (
            BASE_INTEGRITY[FortificationKind.HULL] + level * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        )
        self.assertEqual(fortification.max_integrity, expected_integrity)

        # The hull row feeds hull ONLY — handling and armament are untouched, where the
        # retired placeholder gave all three the same number.
        speed = CapabilityType.objects.get(name=SPEED_CAPABILITY_NAME)
        self.assertEqual(vehicle.unit.effective_capability(speed), ship.effective_handling())
        self.assertEqual(vehicle.unit.strength, ship.effective_armament())

        self.assertTrue(
            MilitaryUnitCapability.objects.filter(
                unit=vehicle.unit.military_unit,
                capability=capability,
            ).exists()
        )

    def test_deploying_a_threaded_ship_mints_no_capability_type(self) -> None:
        """The #2724 corpus-pollution regression: deployment must author nothing.

        Before #2736 this call get_or_create'd a ``sanctum_<resonance>`` CapabilityType,
        so every resonance a player ever levelled added an authored-looking row to the
        exported content corpus — named after other content, so the set could never be
        enumerated ahead of time.

        ``speed`` is pre-created here because the bridge legitimately get_or_create's it:
        it is a single, enumerable row registered in ``seeds/config_prerequisites.py``,
        which is exactly what the resonance-named ones could never be.
        """
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=10)
        _author_capability_row(resonance, CapabilityTypeFactory(), base=2)
        CapabilityTypeFactory(name=SPEED_CAPABILITY_NAME)
        before = CapabilityType.objects.count()

        materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        self.assertEqual(CapabilityType.objects.count(), before)

    def test_unauthored_resonance_grants_no_capability(self) -> None:
        """A woven resonance with no authored row is inert, not an error."""
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        _weave(sanctum, ResonanceFactory(), level=10)

        vehicle = materialize_ship_as_battle_vehicle(ship=ship, battle=self.battle, side=self.side)

        speed = CapabilityType.objects.get(name=SPEED_CAPABILITY_NAME)
        self.assertEqual(
            list(
                MilitaryUnitCapability.objects.filter(unit=vehicle.unit.military_unit).exclude(
                    capability=speed
                )
            ),
            [],
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
