"""Tests for ship_sanctum_bonus + level-3 capability read (#1832 Task 5)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode
from world.room_features.factories import RoomFeatureInstanceFactory
from world.ships.factories import ShipDetailsFactory
from world.ships.sanctum_bonus import ship_sanctum_bonus, ship_sanctum_capabilities
from world.ships.types import ShipStatBonus


def _sanctum_for_ship(ship) -> SanctumDetails:
    room_profile = RoomProfileFactory(area=ship.building.area)
    feature_instance = RoomFeatureInstanceFactory(room_profile=room_profile)
    return SanctumDetails.objects.create(
        feature_instance=feature_instance,
        resonance_type=ResonanceFactory(),
        owner_mode=SanctumOwnerMode.PERSONAL,
    )


class ShipSanctumBonusTests(TestCase):
    def test_no_sanctum_returns_zero_bonus_and_no_capabilities(self) -> None:
        ship = ShipDetailsFactory()

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())
        self.assertEqual(ship_sanctum_capabilities(ship), [])

    def test_woven_thread_contributes_bonus_and_capability_at_level_3(self) -> None:
        ship = ShipDetailsFactory()
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

        bonus = ship_sanctum_bonus(ship)

        self.assertEqual(bonus.hull, 3)
        self.assertEqual(bonus.handling, 3)
        self.assertEqual(bonus.armament, 3)
        self.assertGreater(bonus.handling, 0)

        capabilities = ship_sanctum_capabilities(ship)
        self.assertEqual(capabilities, [resonance])

    def test_sub_level_3_thread_contributes_bonus_but_no_capability(self) -> None:
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            resonance=resonance,
            level=2,
        )

        bonus = ship_sanctum_bonus(ship)

        self.assertEqual(bonus.hull, 2)
        self.assertEqual(ship_sanctum_capabilities(ship), [])

    def test_retired_thread_excluded(self) -> None:
        from django.utils import timezone

        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            resonance=resonance,
            level=5,
            retired_at=timezone.now(),
        )

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())
        self.assertEqual(ship_sanctum_capabilities(ship), [])
