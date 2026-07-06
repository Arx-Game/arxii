"""Condition-tier upkeep tests (#1930): arrears-first, slide/regain/dwell, recovery."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.areas.factories import AreaFactory
from world.buildings.condition_services import (
    ConditionServiceError,
    prepare_building,
    refurbish_building,
    refurbish_cost,
    set_ultra_upkeep,
    settle_upkeep_arrears,
)
from world.buildings.constants import (
    ARREARS_CAP_WEEKS,
    GRACE_MISSES,
    REFURBISH_COPPER_PER_TIER,
    SLIP_WEEKS_PER_TIER,
    ULTRA_UPKEEP_MULTIPLIER,
    ConditionTier,
)
from world.buildings.factories import BuildingFactory
from world.buildings.models import (
    BuildingPolish,
    MothballedRoomState,
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
)
from world.buildings.mothball_services import (
    mothball_building,
    sweep_building_mothballs,
    unmothball_building,
)
from world.buildings.polish_services import apply_project_completion
from world.buildings.upkeep_services import (
    apply_weekly_upkeep_for_building,
    set_condition_tier,
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


def _purse(persona):
    return get_or_create_purse(persona.character_sheet)


def _building_with_upkeep(owner, weekly: int = 10, polish: int = 1000):
    building = _make_building(owner)
    cat = PolishCategory.objects.create(name=f"Opulence-{building.pk}")
    template = _make_template(f"Hall-{building.pk}", [(cat, polish)], weekly_upkeep_cost=weekly)
    apply_project_completion(building, template)
    return building, cat


def _age_condition(building, days: int) -> None:
    building.condition_since = timezone.now() - timedelta(days=days)
    building.save(update_fields=["condition_since"])


class WeeklyUpkeepPaymentTests(TestCase):
    def test_paid_week_resets_misses_and_stays_excellent(self) -> None:
        owner = _make_persona_with_wallet(gold=500)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        building.consecutive_missed_upkeep = 2
        building.save(update_fields=["consecutive_missed_upkeep"])

        paid = apply_weekly_upkeep_for_building(building)

        self.assertTrue(paid)
        wallet = _purse(owner)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 490)
        building.refresh_from_db()
        self.assertEqual(building.consecutive_missed_upkeep, 0)
        self.assertEqual(building.consecutive_paid_upkeep, 1)
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)
        instance = building.project_instances.first()
        self.assertIsNotNone(instance.last_upkeep_paid_at)

    def test_no_instances_is_noop_success(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building = _make_building(owner)
        self.assertTrue(apply_weekly_upkeep_for_building(building))

    def test_mothballed_building_is_frozen(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)
        building.mothballed_at = timezone.now()
        building.save(update_fields=["mothballed_at"])

        paid = apply_weekly_upkeep_for_building(building)

        self.assertTrue(paid)
        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, 0)
        self.assertEqual(building.consecutive_missed_upkeep, 0)


class MissArrearsAndSlideTests(TestCase):
    def test_grace_misses_accrue_arrears_without_slide(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)

        for _ in range(GRACE_MISSES):
            self.assertFalse(apply_weekly_upkeep_for_building(building))

        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, 100 * GRACE_MISSES)
        self.assertEqual(building.consecutive_missed_upkeep, GRACE_MISSES)
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)

    def test_first_slide_lands_after_grace_plus_slip_window(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)
        first_slide_week = GRACE_MISSES + SLIP_WEEKS_PER_TIER

        for _ in range(first_slide_week - 1):
            apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)

        apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.GOOD)

    def test_arrears_cap(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)

        for _ in range(ARREARS_CAP_WEEKS + 5):
            apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, 100 * ARREARS_CAP_WEEKS)

    def test_condition_floors_at_decayed(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)
        set_condition_tier(building, ConditionTier.DECAYED)

        for _ in range(GRACE_MISSES + SLIP_WEEKS_PER_TIER * 2):
            apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.DECAYED)

    def test_missed_week_above_excellent_drops_to_excellent(self) -> None:
        owner = _make_persona_with_wallet(gold=0)
        building, _cat = _building_with_upkeep(owner, weekly=100)
        set_condition_tier(building, ConditionTier.EXTRAVAGANT)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)
        self.assertEqual(building.upkeep_arrears, 100)


class RegainTests(TestCase):
    def test_paid_weeks_climb_one_tier_per_regain_window(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.WORN)

        apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.WORN)

        apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.FINE)
        self.assertEqual(building.consecutive_paid_upkeep, 0)

    def test_regain_never_exceeds_excellent(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.GOOD)

        for _ in range(10):
            apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)


class DwellDecayTests(TestCase):
    def test_extravagant_slides_to_excellent_after_dwell(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.EXTRAVAGANT)
        _age_condition(building, days=8)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)

    def test_fresh_extravagant_survives_the_week(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.EXTRAVAGANT)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXTRAVAGANT)

    def test_immaculate_without_ultra_slides_one_tier(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.IMMACULATE)
        _age_condition(building, days=8)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXTRAVAGANT)

    def test_immaculate_with_ultra_holds_and_charges_premium(self) -> None:
        owner = _make_persona_with_wallet(gold=10_000)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.IMMACULATE)
        set_ultra_upkeep(building=building, enabled=True)
        _age_condition(building, days=8)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.IMMACULATE)
        wallet = _purse(owner)
        wallet.refresh_from_db()
        premium = ULTRA_UPKEEP_MULTIPLIER * 10
        self.assertEqual(wallet.balance, 10_000 - premium - 10)

    def test_immaculate_with_ultra_but_premium_unaffordable_slides_one_tier(self) -> None:
        # 15 coppers: enough for the normal weekly 10, not the 40 premium —
        # the ultra hold lapses (one-tier slide) but the paid week keeps the
        # building from dropping further.
        owner = _make_persona_with_wallet(gold=15)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.IMMACULATE)
        set_ultra_upkeep(building=building, enabled=True)
        _age_condition(building, days=8)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXTRAVAGANT)

    def test_immaculate_broke_owner_loses_shine_entirely(self) -> None:
        # Can't pay the premium OR the normal upkeep: dwell slide + the
        # missed-week drop compound to EXCELLENT in one cycle.
        owner = _make_persona_with_wallet(gold=5)
        building, _cat = _building_with_upkeep(owner, weekly=10)
        set_condition_tier(building, ConditionTier.IMMACULATE)
        set_ultra_upkeep(building=building, enabled=True)
        _age_condition(building, days=8)

        apply_weekly_upkeep_for_building(building)

        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)
        self.assertEqual(building.upkeep_arrears, 10)


class ConditionServiceTests(TestCase):
    def test_settle_pays_arrears_to_zero(self) -> None:
        owner = _make_persona_with_wallet(gold=1_000)
        building, _cat = _building_with_upkeep(owner)
        building.upkeep_arrears = 300
        building.save(update_fields=["upkeep_arrears"])

        paid = settle_upkeep_arrears(building=building, payer_purse=_purse(owner))

        self.assertEqual(paid, 300)
        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, 0)

    def test_settle_insufficient_funds_leaves_arrears(self) -> None:
        owner = _make_persona_with_wallet(gold=10)
        building, _cat = _building_with_upkeep(owner)
        building.upkeep_arrears = 300
        building.save(update_fields=["upkeep_arrears"])

        with self.assertRaises(ValidationError):
            settle_upkeep_arrears(building=building, payer_purse=_purse(owner))
        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, 300)

    def test_refurbish_restores_to_excellent_and_charges_by_deficit(self) -> None:
        owner = _make_persona_with_wallet(gold=100_000)
        building, _cat = _building_with_upkeep(owner)
        set_condition_tier(building, ConditionTier.WORN)
        expected = REFURBISH_COPPER_PER_TIER * 3 * building.target_size
        self.assertEqual(refurbish_cost(building), expected)

        cost = refurbish_building(building=building, payer_purse=_purse(owner))

        self.assertEqual(cost, expected)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)

    def test_refurbish_refused_with_arrears_or_at_excellent(self) -> None:
        owner = _make_persona_with_wallet(gold=100_000)
        building, _cat = _building_with_upkeep(owner)
        building.upkeep_arrears = 50
        building.save(update_fields=["upkeep_arrears"])
        with self.assertRaises(ConditionServiceError):
            refurbish_building(building=building, payer_purse=_purse(owner))

        building.upkeep_arrears = 0
        building.save(update_fields=["upkeep_arrears"])
        with self.assertRaises(ConditionServiceError):
            refurbish_building(building=building, payer_purse=_purse(owner))

    def test_prepare_climbs_excellent_to_immaculate_then_refuses(self) -> None:
        owner = _make_persona_with_wallet(gold=1_000_000)
        building, _cat = _building_with_upkeep(owner)

        tier = prepare_building(building=building, payer_purse=_purse(owner))
        self.assertEqual(tier, ConditionTier.EXTRAVAGANT)
        tier = prepare_building(building=building, payer_purse=_purse(owner))
        self.assertEqual(tier, ConditionTier.IMMACULATE)
        with self.assertRaises(ConditionServiceError):
            prepare_building(building=building, payer_purse=_purse(owner))

    def test_prepare_refused_below_excellent(self) -> None:
        owner = _make_persona_with_wallet(gold=1_000_000)
        building, _cat = _building_with_upkeep(owner)
        set_condition_tier(building, ConditionTier.GOOD)
        with self.assertRaises(ConditionServiceError):
            prepare_building(building=building, payer_purse=_purse(owner))


class PrestigeModulationTests(TestCase):
    def _home_in(self, building, owner):
        from world.locations.constants import HolderType, LocationParentType
        from world.locations.models import LocationTenancy

        home = RoomProfileFactory(area=building.area)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=home,
            tenant_type=HolderType.PERSONA,
            tenant_persona=owner,
            is_primary_home=True,
        )
        return home

    def test_condition_tier_step_modulates_building_polish(self) -> None:
        owner = _make_persona_with_wallet()
        building, _cat = _building_with_upkeep(owner, polish=1000)
        self._home_in(building, owner)

        set_condition_tier(building, ConditionTier.EXCELLENT)
        owner.refresh_from_db()
        # set_condition_tier no-ops on same tier; force a recompute.
        from world.buildings.polish_services import (
            recompute_persona_prestige_from_dwellings,
        )

        self.assertEqual(recompute_persona_prestige_from_dwellings(owner), 1000)

        set_condition_tier(building, ConditionTier.WORN)
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 400)

        set_condition_tier(building, ConditionTier.IMMACULATE)
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 2000)

    def test_room_polish_follows_containing_building_condition(self) -> None:
        from world.buildings.polish_services import apply_room_polish_delta

        owner = _make_persona_with_wallet()
        building, cat = _building_with_upkeep(owner, polish=0)
        BuildingPolish.objects.filter(building=building).delete()
        home = self._home_in(building, owner)
        apply_room_polish_delta(home, cat, 500)

        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 500)

        set_condition_tier(building, ConditionTier.RAMSHACKLE)
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 100)


class MothballTests(TestCase):
    def test_mothball_snapshots_and_hides_mixed_rooms(self) -> None:
        owner = _make_persona_with_wallet()
        building = _make_building(owner)
        public_room = RoomProfileFactory(area=building.area, is_public=True)
        private_room = RoomProfileFactory(area=building.area, is_public=False)

        hidden = mothball_building(building)

        self.assertEqual(hidden, 1)
        building.refresh_from_db()
        self.assertIsNotNone(building.mothballed_at)
        public_room.refresh_from_db()
        private_room.refresh_from_db()
        self.assertFalse(public_room.is_public)
        self.assertFalse(private_room.is_public)
        self.assertEqual(MothballedRoomState.objects.filter(building=building).count(), 2)

    def test_unmothball_restores_mixed_rooms_and_clears_state(self) -> None:
        owner = _make_persona_with_wallet()
        building = _make_building(owner)
        public_room = RoomProfileFactory(area=building.area, is_public=True)
        private_room = RoomProfileFactory(area=building.area, is_public=False)
        mothball_building(building)
        building.consecutive_missed_upkeep = 3
        building.save(update_fields=["consecutive_missed_upkeep"])

        restored = unmothball_building(building)

        self.assertEqual(restored, 2)
        building.refresh_from_db()
        self.assertIsNone(building.mothballed_at)
        self.assertEqual(building.consecutive_missed_upkeep, 0)
        public_room.refresh_from_db()
        private_room.refresh_from_db()
        self.assertTrue(public_room.is_public)
        self.assertFalse(private_room.is_public)
        self.assertFalse(MothballedRoomState.objects.filter(building=building).exists())

    def test_sweep_mothballs_long_inactive_and_restores_returned(self) -> None:
        owner = _make_persona_with_wallet()
        building = _make_building(owner)
        RoomProfileFactory(area=building.area, is_public=True)

        with mock.patch(
            "world.buildings.mothball_services._owner_is_long_inactive", return_value=True
        ):
            stats = sweep_building_mothballs()
        self.assertEqual(stats["mothballed"], 1)
        building.refresh_from_db()
        self.assertIsNotNone(building.mothballed_at)

        with mock.patch(
            "world.buildings.mothball_services._owner_is_long_inactive", return_value=False
        ):
            stats = sweep_building_mothballs()
        self.assertEqual(stats["restored"], 1)
        building.refresh_from_db()
        self.assertIsNone(building.mothballed_at)


class ConditionJourneyTests(TestCase):
    """The primary journey arc from the #1930 spec's test seams."""

    def test_neglect_return_settle_refurbish_prepare_arc(self) -> None:
        owner = _make_persona_with_wallet(gold=100)
        building, _cat = _building_with_upkeep(owner, weekly=100, polish=1000)

        # Week 1: affordable → paid, Excellent holds.
        self.assertTrue(apply_weekly_upkeep_for_building(building))

        # Grace misses: arrears only.
        for _ in range(GRACE_MISSES):
            self.assertFalse(apply_weekly_upkeep_for_building(building))
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)
        self.assertEqual(building.upkeep_arrears, 100 * GRACE_MISSES)

        # Sustained neglect: first slide lands.
        for _ in range(SLIP_WEEKS_PER_TIER):
            apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.GOOD)

        # Long inactivity → mothballed: frozen, bounded bill.
        mothball_building(building)
        arrears_at_mothball = building.upkeep_arrears
        for _ in range(10):
            apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.upkeep_arrears, arrears_at_mothball)

        # Return: restore, settle, refurbish, prepare to the gala peak.
        unmothball_building(building)
        transfer(amount=1_000_000, reason="windfall", to_purse=_purse(owner))
        settle_upkeep_arrears(building=building, payer_purse=_purse(owner))
        refurbish_building(building=building, payer_purse=_purse(owner))
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXCELLENT)

        prepare_building(building=building, payer_purse=_purse(owner))
        prepare_building(building=building, payer_purse=_purse(owner))
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.IMMACULATE)
        owner.refresh_from_db()
        self.assertEqual(owner.prestige_from_dwellings, 0)  # home not in this building

        # The shine is temporary: dwell lapses without ultra upkeep.
        _age_condition(building, days=8)
        apply_weekly_upkeep_for_building(building)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, ConditionTier.EXTRAVAGANT)
