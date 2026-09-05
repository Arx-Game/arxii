"""Area elevation tests (#696 gap 3): the earned, player-declared level increase."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.definitions.areas import DeclareElevationAction
from world.areas.constants import AreaLevel
from world.areas.elevation_services import (
    declare_elevation,
    elevation_eligibility,
    held_building_count,
    next_level,
)
from world.areas.factories import AreaFactory
from world.areas.models import AreaElevationRequirement
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.locations.constants import StatKey
from world.locations.factories import LocationOwnershipFactory, LocationValueModifierFactory


class NextLevelTests(TestCase):
    def test_next_level_steps_up_one_rung(self) -> None:
        area = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        self.assertEqual(next_level(area), AreaLevel.WARD)

    def test_next_level_none_at_ceiling(self) -> None:
        area = AreaFactory(level=AreaLevel.PLANE)
        self.assertIsNone(next_level(area))


class ElevationEligibilityTests(TestCase):
    def setUp(self) -> None:
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        self.building_a = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)
        self.building_b = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)
        self.building_c = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)

        self.declarer_sheet = CharacterSheetFactory()
        self.declarer = self.declarer_sheet.primary_persona
        self.outsider_sheet = CharacterSheetFactory()
        self.outsider = self.outsider_sheet.primary_persona

        LocationOwnershipFactory(area=self.building_a, holder_persona=self.declarer)
        LocationOwnershipFactory(area=self.building_b, holder_persona=self.declarer)
        LocationOwnershipFactory(area=self.building_c, holder_persona=self.outsider)

        self.requirement = AreaElevationRequirement.objects.create(
            to_level=AreaLevel.WARD,
            min_held_buildings=2,
            min_order_stat=10,
            cost_coppers=500,
        )

    def _set_order(self, value: int) -> None:
        LocationValueModifierFactory(area=self.neighborhood, stat_key=StatKey.ORDER, value=value)

    def test_held_building_count_counts_only_declarers_holdings(self) -> None:
        self.assertEqual(held_building_count(self.neighborhood, declarer=self.declarer), 2)
        self.assertEqual(held_building_count(self.neighborhood, declarer=self.outsider), 1)

    def test_ineligible_below_building_threshold(self) -> None:
        self._set_order(10)
        result = elevation_eligibility(self.neighborhood, declarer=self.outsider)
        self.assertFalse(result.eligible)
        self.assertEqual(result.held_buildings, 1)
        self.assertTrue(any("buildings" in reason for reason in result.reasons))

    def test_ineligible_below_order_threshold(self) -> None:
        self._set_order(3)
        result = elevation_eligibility(self.neighborhood, declarer=self.declarer)
        self.assertFalse(result.eligible)
        self.assertEqual(result.order_stat, 3)
        self.assertTrue(any("order" in reason for reason in result.reasons))

    def test_eligible_when_all_thresholds_met(self) -> None:
        self._set_order(10)
        result = elevation_eligibility(self.neighborhood, declarer=self.declarer)
        self.assertTrue(result.eligible, result.reasons)
        self.assertEqual(result.reasons, [])
        self.assertEqual(result.requirement, self.requirement)

    def test_no_requirement_configured_for_next_level(self) -> None:
        self._set_order(10)
        ward = AreaFactory(level=AreaLevel.WARD, parent=None)
        # No AreaElevationRequirement seeded for CITY.
        result = elevation_eligibility(ward, declarer=self.declarer)
        self.assertFalse(result.eligible)
        self.assertIsNone(result.requirement)
        self.assertTrue(any("is configured" in reason for reason in result.reasons))

    def test_already_at_ceiling(self) -> None:
        plane = AreaFactory(level=AreaLevel.PLANE)
        result = elevation_eligibility(plane, declarer=self.declarer)
        self.assertFalse(result.eligible)
        self.assertIsNone(result.requirement)
        self.assertTrue(any("highest level" in reason for reason in result.reasons))


class DeclareElevationServiceTests(TestCase):
    def setUp(self) -> None:
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        self.building_a = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)
        self.building_b = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)

        self.declarer_sheet = CharacterSheetFactory()
        self.declarer = self.declarer_sheet.primary_persona
        LocationOwnershipFactory(area=self.building_a, holder_persona=self.declarer)
        LocationOwnershipFactory(area=self.building_b, holder_persona=self.declarer)
        LocationValueModifierFactory(area=self.neighborhood, stat_key=StatKey.ORDER, value=10)

        AreaElevationRequirement.objects.create(
            to_level=AreaLevel.WARD,
            min_held_buildings=2,
            min_order_stat=10,
            cost_coppers=500,
        )

        self.purse = get_or_create_purse(self.declarer_sheet)
        self.purse.balance = 10000
        self.purse.save(update_fields=["balance"])

    def test_declare_writes_level_and_charges_cost(self) -> None:
        declare_elevation(self.neighborhood, declarer=self.declarer, treasury_or_purse=self.purse)
        self.neighborhood.refresh_from_db()
        self.assertEqual(self.neighborhood.level, AreaLevel.WARD)
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 10000 - 500)

    def test_declare_refused_for_non_holder(self) -> None:
        outsider_sheet = CharacterSheetFactory()
        outsider = outsider_sheet.primary_persona
        outsider_purse = get_or_create_purse(outsider_sheet)
        outsider_purse.balance = 10000
        outsider_purse.save(update_fields=["balance"])

        with self.assertRaises(ValidationError):
            declare_elevation(
                self.neighborhood, declarer=outsider, treasury_or_purse=outsider_purse
            )
        self.neighborhood.refresh_from_db()
        self.assertEqual(self.neighborhood.level, AreaLevel.NEIGHBORHOOD)

    def test_second_declare_recomputes_against_next_requirement(self) -> None:
        declare_elevation(self.neighborhood, declarer=self.declarer, treasury_or_purse=self.purse)
        self.neighborhood.refresh_from_db()
        self.assertEqual(self.neighborhood.level, AreaLevel.WARD)

        # No AreaElevationRequirement seeded for CITY (the new next level).
        result = elevation_eligibility(self.neighborhood, declarer=self.declarer)
        self.assertFalse(result.eligible)
        self.assertIsNone(result.requirement)
        self.assertTrue(any("is configured" in reason for reason in result.reasons))

        with self.assertRaises(ValidationError):
            declare_elevation(
                self.neighborhood, declarer=self.declarer, treasury_or_purse=self.purse
            )


class DeclareElevationActionTests(TestCase):
    def setUp(self) -> None:
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        self.building_a = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)
        self.building_b = AreaFactory(level=AreaLevel.BUILDING, parent=self.neighborhood)

        self.declarer_sheet = CharacterSheetFactory()
        self.declarer = self.declarer_sheet.primary_persona
        self.actor = self.declarer_sheet.character

        LocationOwnershipFactory(area=self.building_a, holder_persona=self.declarer)
        LocationOwnershipFactory(area=self.building_b, holder_persona=self.declarer)
        LocationValueModifierFactory(area=self.neighborhood, stat_key=StatKey.ORDER, value=10)
        # DeclareElevationAction's own gate: the declarer must be the AREA's
        # (not just its buildings') effective owner.
        LocationOwnershipFactory(area=self.neighborhood, holder_persona=self.declarer)

        AreaElevationRequirement.objects.create(
            to_level=AreaLevel.WARD,
            min_held_buildings=2,
            min_order_stat=10,
            cost_coppers=500,
        )

        purse = get_or_create_purse(self.declarer_sheet)
        purse.balance = 10000
        purse.save(update_fields=["balance"])

        self.outsider_sheet = CharacterSheetFactory()
        self.outsider_actor = self.outsider_sheet.character

    def test_dispatch_via_run_with_plain_int_kwargs(self) -> None:
        result = DeclareElevationAction().run(actor=self.actor, area_id=self.neighborhood.pk)
        self.assertTrue(result.success, result.message)
        self.neighborhood.refresh_from_db()
        self.assertEqual(self.neighborhood.level, AreaLevel.WARD)

    def test_dispatch_refused_for_non_owner(self) -> None:
        result = DeclareElevationAction().run(
            actor=self.outsider_actor, area_id=self.neighborhood.pk
        )
        self.assertFalse(result.success)
        self.neighborhood.refresh_from_db()
        self.assertEqual(self.neighborhood.level, AreaLevel.NEIGHBORHOOD)

    def test_dispatch_unknown_area(self) -> None:
        result = DeclareElevationAction().run(actor=self.actor, area_id=999999)
        self.assertFalse(result.success)
