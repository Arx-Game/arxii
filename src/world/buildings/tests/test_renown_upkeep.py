"""Phase E tests for upkeep + decay + recovery (#676)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.areas.factories import AreaFactory
from world.buildings.constants import DECAY_BASE_AMOUNT
from world.buildings.factories import BuildingFactory
from world.buildings.models import (
    BuildingPolish,
    BuildingProjectInstancePolish,
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
)
from world.buildings.polish_services import apply_project_completion
from world.buildings.upkeep_services import (
    apply_mass_feature_restoration,
    apply_one_decay_tick,
    apply_restoration_project,
    apply_weekly_upkeep_for_building,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer


def _make_persona_with_wallet(gold: int = 0):
    """Persona whose purse holds ``gold`` coppers (#932: purse ledger)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    if gold:
        transfer(
            amount=gold, reason="test seed", to_purse=get_or_create_purse(character.sheet_data)
        )
    return sheet.primary_persona


def _make_template(name: str, increments: list[tuple[PolishCategory, int]], **kwargs):
    template = ProjectTemplate.objects.create(name=name, **kwargs)
    for category, value in increments:
        ProjectTemplatePolishIncrement.objects.create(
            template=template, category=category, value=value
        )
    return template


def _make_building(owner):
    return BuildingFactory(area=AreaFactory(level=10), owner_persona=owner)


class WeeklyUpkeepPaymentTests(TestCase):
    def test_owner_with_enough_gold_pays_and_resets_counters(self) -> None:
        owner = _make_persona_with_wallet(gold=500)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(cat, 1000)], weekly_upkeep_cost=10)
        instance = apply_project_completion(building, template)
        # Pretend the cron ran and one miss already happened.
        instance.consecutive_missed_upkeep = 3
        instance.save(update_fields=["consecutive_missed_upkeep"])

        paid = apply_weekly_upkeep_for_building(building)

        self.assertTrue(paid)
        wallet = get_or_create_purse(owner.character_sheet)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 490)
        instance.refresh_from_db()
        self.assertEqual(instance.consecutive_missed_upkeep, 0)
        self.assertIsNotNone(instance.last_upkeep_paid_at)

    def test_owner_without_enough_gold_misses_and_decays(self) -> None:
        owner = _make_persona_with_wallet(gold=5)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(cat, 1000)], weekly_upkeep_cost=100)
        instance = apply_project_completion(building, template)

        paid = apply_weekly_upkeep_for_building(building)

        self.assertFalse(paid)
        wallet = get_or_create_purse(owner.character_sheet)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 5)  # nothing deducted on miss
        instance.refresh_from_db()
        self.assertEqual(instance.consecutive_missed_upkeep, 1)
        # First miss decays by DECAY_BASE_AMOUNT.
        bp = BuildingPolish.objects.get(building=building, category=cat)
        self.assertEqual(bp.value, 1000 - DECAY_BASE_AMOUNT)

    def test_no_owner_misses_and_decays(self) -> None:
        building = BuildingFactory(area=AreaFactory(level=10), owner_persona=None)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(cat, 1000)], weekly_upkeep_cost=10)
        apply_project_completion(building, template)
        paid = apply_weekly_upkeep_for_building(building)
        self.assertFalse(paid)

    def test_no_active_instances_is_noop_success(self) -> None:
        """Building with no project instances has nothing to upkeep."""
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        paid = apply_weekly_upkeep_for_building(building)
        self.assertTrue(paid)


class DecayCurveTests(TestCase):
    def test_decay_accelerates_with_consecutive_misses(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(cat, 10_000)], weekly_upkeep_cost=10)
        apply_project_completion(building, template)

        # 3 missed ticks: base, base*1.5, base*2.25
        apply_one_decay_tick(building)
        apply_one_decay_tick(building)
        apply_one_decay_tick(building)

        # Expected polish reduction:
        # tick1: 50, tick2: 75, tick3: 112 = 237 total
        bp = BuildingPolish.objects.get(building=building, category=cat)
        self.assertLess(bp.value, 10_000)
        # The reduction should be > base (acceleration verified).
        reduction = 10_000 - bp.value
        self.assertGreater(reduction, DECAY_BASE_AMOUNT * 3)

    def test_decay_moves_to_next_priority_when_outermost_zeroes(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        # Outermost template (lower decay_priority = outermost = decays first).
        outer = _make_template("Outer", [(cat, 30)], decay_priority=10)
        inner = _make_template("Inner", [(cat, 1000)], decay_priority=100)
        outer_inst = apply_project_completion(building, outer)
        inner_inst = apply_project_completion(building, inner)

        # First tick should decay the outermost (lower priority).
        # Outer has 30 polish, base decay is 50 → drains outer to 0 in one tick.
        apply_one_decay_tick(building)

        outer_inst.refresh_from_db()
        inner_inst.refresh_from_db()
        self.assertIsNotNone(outer_inst.decayed_at)
        # Outer's counter reset for the next-priority instance's fresh start.
        self.assertEqual(outer_inst.consecutive_missed_upkeep, 0)
        # Inner still untouched.
        outer_polish = BuildingProjectInstancePolish.objects.get(instance=outer_inst, category=cat)
        inner_polish = BuildingProjectInstancePolish.objects.get(instance=inner_inst, category=cat)
        self.assertEqual(outer_polish.value, 0)
        self.assertEqual(inner_polish.value, 1000)

        # Next tick targets inner now (outer no longer active).
        apply_one_decay_tick(building)
        inner_inst.refresh_from_db()
        self.assertEqual(inner_inst.consecutive_missed_upkeep, 1)


class DormancyTests(TestCase):
    def test_all_instances_decayed_flips_to_dormant(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        # One instance with tiny polish → decays in one weekly cycle.
        template = _make_template("Fragile", [(cat, 30)], weekly_upkeep_cost=10)
        apply_project_completion(building, template)

        # Miss the upkeep; tick decay drains the instance + flips dormancy.
        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertFalse(building.is_accessible)
        self.assertIsNotNone(building.dormant_since)

    def test_partial_decay_does_not_flip_dormancy(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Big", [(cat, 10_000)], weekly_upkeep_cost=10)
        apply_project_completion(building, template)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertTrue(building.is_accessible)
        self.assertIsNone(building.dormant_since)


class RestorationTests(TestCase):
    def test_restoration_project_clears_dormancy(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        building.is_accessible = False
        building.dormant_since = timezone.now()
        building.save(update_fields=["is_accessible", "dormant_since"])

        flipped = apply_restoration_project(building)

        self.assertTrue(flipped)
        building.refresh_from_db()
        self.assertTrue(building.is_accessible)
        self.assertIsNone(building.dormant_since)

    def test_restoration_on_accessible_building_is_noop(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        flipped = apply_restoration_project(building)
        self.assertFalse(flipped)

    def test_mass_restoration_refills_decayed_instances(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        cat = PolishCategory.objects.create(name="Opulence")
        template = _make_template("Hall", [(cat, 1500)], weekly_upkeep_cost=10)
        instance = apply_project_completion(building, template)
        # Manually mark instance decayed.
        BuildingProjectInstancePolish.objects.filter(instance=instance).update(value=0)
        instance.decayed_at = timezone.now()
        instance.save(update_fields=["decayed_at"])
        # Also rebuild aggregate to reflect the drain.
        BuildingPolish.objects.filter(building=building).update(value=0)

        restored_count = apply_mass_feature_restoration(building)

        self.assertEqual(restored_count, 1)
        instance.refresh_from_db()
        self.assertIsNone(instance.decayed_at)
        ip = BuildingProjectInstancePolish.objects.get(instance=instance, category=cat)
        self.assertEqual(ip.value, 1500)
        # Aggregate matches.
        bp = BuildingPolish.objects.get(building=building, category=cat)
        self.assertEqual(bp.value, 1500)
        # Owner's prestige re-credited.
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 1500)

    def test_mass_restoration_with_no_decayed_is_noop(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        restored_count = apply_mass_feature_restoration(building)
        self.assertEqual(restored_count, 0)
