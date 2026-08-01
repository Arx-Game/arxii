"""Tests for ship_sanctum_bonus + ship_sanctum_capability_grants.

#1832 Task 5 built these off placeholders (``hull = handling = armament = sum of levels``
and a level-3 flag). #2736 moved both onto the authored ``ThreadPullEffect`` catalog,
so every case here authors the rows it expects to be paid for — an unauthored
resonance is inert by design, not by accident.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.conditions.factories import CapabilityTypeFactory
from world.magic.constants import SanctumSlotKind, VitalBonusTarget
from world.magic.factories import ResonanceFactory
from world.magic.models import CapabilityPowerConfig
from world.room_features.factories import RoomFeatureInstanceFactory
from world.ships.factories import ShipDetailsFactory
from world.ships.sanctum_bonus import ship_sanctum_bonus, ship_sanctum_capability_grants
from world.ships.tests._sanctum_catalog import (
    author_capability_row as _author_capability_row,
    author_stat_row as _author_stat_row,
    sanctum_for_ship as _sanctum_for_ship,
    weave as _weave,
)
from world.ships.types import ShipStatBonus


class ShipSanctumStatBonusTests(TestCase):
    """The stat half: authored ``SHIP_*`` VITAL_BONUS rows, scaled by thread depth."""

    def test_no_sanctum_returns_zero_bonus_and_no_capabilities(self) -> None:
        ship = ShipDetailsFactory()

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())
        self.assertEqual(ship_sanctum_capability_grants(ship), [])

    def test_unauthored_resonance_grants_nothing(self) -> None:
        """A woven thread with no authored row is inert — not an error (#2736).

        Under the pre-#2736 placeholder this same setup paid hull=handling=armament=5.
        """
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        _weave(sanctum, ResonanceFactory(), level=5)

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())
        self.assertEqual(ship_sanctum_capability_grants(ship), [])

    def test_authored_row_feeds_only_its_own_stat(self) -> None:
        """Each resonance leans into one stat — no more identical hull/handling/armament."""
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=20)
        _author_stat_row(resonance, VitalBonusTarget.SHIP_HANDLING, 4)

        bonus = ship_sanctum_bonus(ship)

        # thread_level_multiplier(20) == 2, so 4 x 2.
        self.assertEqual(bonus.handling, 8)
        self.assertEqual(bonus.hull, 0)
        self.assertEqual(bonus.armament, 0)

    def test_deeper_thread_gives_more(self) -> None:
        ship_shallow = ShipDetailsFactory()
        ship_deep = ShipDetailsFactory()
        resonance = ResonanceFactory()
        _author_stat_row(resonance, VitalBonusTarget.SHIP_HULL, 5)
        _weave(_sanctum_for_ship(ship_shallow), resonance, level=10)
        _weave(_sanctum_for_ship(ship_deep), resonance, level=30)

        self.assertGreater(
            ship_sanctum_bonus(ship_deep).hull, ship_sanctum_bonus(ship_shallow).hull
        )

    def test_distinct_resonances_sum_per_stat(self) -> None:
        """Two shrines' worth of stat points add — these are stats, not a capability."""
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        hull_resonance = ResonanceFactory()
        armament_resonance = ResonanceFactory()
        _weave(sanctum, hull_resonance, level=10)
        _weave(sanctum, armament_resonance, level=10, slot=SanctumSlotKind.HELPER)
        _author_stat_row(hull_resonance, VitalBonusTarget.SHIP_HULL, 3)
        _author_stat_row(armament_resonance, VitalBonusTarget.SHIP_ARMAMENT, 6)

        bonus = ship_sanctum_bonus(ship)

        self.assertEqual(bonus.hull, 3)
        self.assertEqual(bonus.armament, 6)
        self.assertEqual(bonus.handling, 0)

    def test_character_vital_row_is_not_a_ship_stat(self) -> None:
        """A MAX_HEALTH row authored on a Sanctum resonance is the weaver's, not the ship's."""
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=20)
        _author_stat_row(resonance, VitalBonusTarget.MAX_HEALTH, 50)

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())

    def test_min_thread_level_gates_the_row(self) -> None:
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=2)
        _author_stat_row(resonance, VitalBonusTarget.SHIP_HULL, 9, min_thread_level=3)

        self.assertEqual(ship_sanctum_bonus(ship).hull, 0)

    def test_retired_thread_excluded(self) -> None:
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=5, retired_at=timezone.now())
        _author_stat_row(resonance, VitalBonusTarget.SHIP_HULL, 5)

        self.assertEqual(ship_sanctum_bonus(ship), ShipStatBonus())
        self.assertEqual(ship_sanctum_capability_grants(ship), [])

    def test_siege_deck_armament_survives_the_rewrite(self) -> None:
        """#675's Siege Deck bonus is independent of any sanctum and still applies."""
        from world.room_features.seeds import ensure_siege_deck_kind
        from world.ships.constants import SIEGE_DECK_ARMAMENT_PER_LEVEL

        ship = ShipDetailsFactory()
        RoomFeatureInstanceFactory(
            room_profile=RoomProfileFactory(area=ship.building.area),
            feature_kind=ensure_siege_deck_kind(),
            level=2,
        )

        bonus = ship_sanctum_bonus(ship)

        self.assertEqual(bonus.armament, 2 * SIEGE_DECK_ARMAMENT_PER_LEVEL)
        self.assertEqual(bonus.hull, 0)


class ShipSanctumCapabilityGrantTests(TestCase):
    """The capability half: authored rows only, curved — never a minted name at a flat 1."""

    def test_authored_row_grants_that_capability(self) -> None:
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        capability = CapabilityTypeFactory(name="traversal")
        _weave(sanctum, resonance, level=3)
        _author_capability_row(resonance, capability, base=2)

        grants = ship_sanctum_capability_grants(ship)

        self.assertEqual([g.capability for g in grants], [capability])
        self.assertGreaterEqual(grants[0].value, 2)

    def test_below_min_thread_level_grants_nothing(self) -> None:
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        _weave(sanctum, resonance, level=2)
        _author_capability_row(resonance, CapabilityTypeFactory(), min_thread_level=3)

        self.assertEqual(ship_sanctum_capability_grants(ship), [])

    def test_deeper_thread_grants_strictly_more(self) -> None:
        """The curve is wired: level 6 beats level 3 off ONE authored row.

        Needs a ``CapabilityPowerConfig`` row and a sanctum level above 0 —
        ``apply_capability_curve`` is inert without both, by design.
        """
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        resonance = ResonanceFactory()
        capability = CapabilityTypeFactory()
        _author_capability_row(resonance, capability, base=4)

        ship_shallow = ShipDetailsFactory()
        ship_deep = ShipDetailsFactory()
        _weave(_sanctum_for_ship(ship_shallow, level=5), resonance, level=3)
        _weave(_sanctum_for_ship(ship_deep, level=5), resonance, level=6)

        shallow = ship_sanctum_capability_grants(ship_shallow)[0].value
        deep = ship_sanctum_capability_grants(ship_deep)[0].value

        self.assertGreater(deep, shallow)

    def test_deeper_authored_unlock_supersedes_the_shallow_one(self) -> None:
        """Highest qualifying min_thread_level wins, so content can author a second tier."""
        ship = ShipDetailsFactory()
        sanctum = _sanctum_for_ship(ship)
        resonance = ResonanceFactory()
        shallow_capability = CapabilityTypeFactory(name="movement")
        deep_capability = CapabilityTypeFactory(name="teleport")
        _weave(sanctum, resonance, level=6)
        _author_capability_row(resonance, shallow_capability, min_thread_level=3)
        _author_capability_row(resonance, deep_capability, min_thread_level=6)

        grants = ship_sanctum_capability_grants(ship)

        self.assertEqual([g.capability for g in grants], [deep_capability])

    def test_query_count_flat_in_resonance_count(self) -> None:
        """Several woven resonances resolve in a bounded query count — no per-grant N+1."""

        def _deploy_ship(resonance_count: int) -> int:
            ship = ShipDetailsFactory()
            sanctum = _sanctum_for_ship(ship)
            slots = [SanctumSlotKind.PERSONAL_OWN, SanctumSlotKind.COVENANT] + [
                SanctumSlotKind.HELPER
            ] * resonance_count
            for index in range(resonance_count):
                resonance = ResonanceFactory()
                _weave(sanctum, resonance, level=3, slot=slots[index])
                _author_capability_row(resonance, CapabilityTypeFactory())
            with CaptureQueriesContext(connection) as ctx:
                ship_sanctum_capability_grants(ship)
            return len(ctx.captured_queries)

        self.assertEqual(_deploy_ship(1), _deploy_ship(4))
