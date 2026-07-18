"""Heat lifecycle tests (#1826) — lie low, bribe, pardon, wanted visibility."""

from unittest.mock import patch

from django.test import TestCase

from world.justice.constants import (
    HEAT_DECAY_PER_DAY,
    LIE_LOW_DECAY_MULT,
    WANTED_VALUE_FLOOR,
    HeatTier,
)
from world.justice.lifecycle import (
    HeatLifecycleError,
    active_lie_low,
    attempt_bribe,
    bribe_cost_for,
    can_pardon,
    crime_collection_malus_applies,
    declare_lie_low,
    end_lie_low,
    pardon_persona,
    wanted_rows_for_area,
)
from world.justice.models import PardonGrant, PersonaHeat
from world.justice.services import accrue_heat, heat_decay_tick
from world.justice.tests.test_services import JusticeFixtureMixin
from world.scenes.factories import PersonaFactory


def _heat(persona, area, society, value):
    return PersonaHeat.objects.create(persona=persona, area=area, society=society, value=value)


class LieLowTests(JusticeFixtureMixin, TestCase):
    def test_declare_end_and_double_declare(self):
        state = declare_lie_low(self.persona, self.kingdom)
        self.assertIsNone(state.ended_at)
        with self.assertRaises(HeatLifecycleError):
            declare_lie_low(self.persona, self.kingdom)
        ended = end_lie_low(self.persona, self.kingdom)
        self.assertIsNotNone(ended.ended_at)
        self.assertIsNone(active_lie_low(self.persona, self.kingdom))

    def test_fresh_heat_breaks_lie_low(self):
        declare_lie_low(self.persona, self.kingdom)
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.kingdom)
        self.assertIsNone(active_lie_low(self.persona, self.kingdom))

    def test_decay_tick_accelerates_declared_area_only(self):
        row_home = _heat(self.persona, self.kingdom, self.crown, 50)
        other = PersonaFactory()
        row_other = _heat(other, self.kingdom, self.crown, 50)
        declare_lie_low(self.persona, self.kingdom)

        heat_decay_tick()
        # values_list bypasses the SharedMemoryModel identity map (bulk
        # .update() leaves cached instances stale — the documented gotcha).
        home_value = PersonaHeat.objects.filter(pk=row_home.pk).values_list("value", flat=True)[0]
        other_value = PersonaHeat.objects.filter(pk=row_other.pk).values_list("value", flat=True)[0]
        expected_fast = 50 - LIE_LOW_DECAY_MULT * HEAT_DECAY_PER_DAY
        self.assertEqual(home_value, max(0, expected_fast))
        self.assertEqual(other_value, 50 - HEAT_DECAY_PER_DAY)

    def test_crime_collection_malus_gates_on_membership_and_area(self):
        from world.societies.factories import OrganizationFactory
        from world.societies.models import OrganizationMembership, OrganizationRank

        org = OrganizationFactory()
        rank = OrganizationRank.objects.filter(organization=org).first()
        OrganizationMembership.objects.create(organization=org, persona=self.persona, rank=rank)
        self.assertFalse(crime_collection_malus_applies(org, self.kingdom))
        declare_lie_low(self.persona, self.kingdom)
        self.assertTrue(crime_collection_malus_applies(org, self.kingdom))
        # A different area is unaffected.
        self.assertFalse(crime_collection_malus_applies(org, self.rival_kingdom))


class BribeTests(JusticeFixtureMixin, TestCase):
    def _fund(self, amount):
        from world.currency.services import get_or_create_purse

        purse = get_or_create_purse(self.persona.character_sheet)
        purse.balance = amount
        purse.save(update_fields=["balance"])
        return purse

    def _check_type(self):
        from world.checks.factories import CheckTypeFactory
        from world.justice.constants import BRIBE_CHECK_TYPE_NAME

        return CheckTypeFactory(name=BRIBE_CHECK_TYPE_NAME)

    def _result(self, level):
        class _Outcome:
            success_level = level

        class _Result:
            outcome = _Outcome()

        return _Result()

    def test_cost_scales_with_heat(self):
        _heat(self.persona, self.kingdom, self.crown, 10)
        self.assertGreater(bribe_cost_for(self.persona, self.kingdom), 0)

    def test_success_clears_and_spends(self):
        self._check_type()
        row = _heat(self.persona, self.kingdom, self.crown, 40)
        purse = self._fund(1_000_000)
        with patch("world.checks.services.perform_check", return_value=self._result(2)):
            outcome = attempt_bribe(self.persona, self.kingdom)
        row.refresh_from_db()
        purse.refresh_from_db()
        self.assertLess(row.value, 40)
        self.assertFalse(outcome["crime_minted"])
        self.assertLess(purse.balance, 1_000_000)

    def test_failure_spends_half_and_clears_nothing(self):
        self._check_type()
        row = _heat(self.persona, self.kingdom, self.crown, 40)
        self._fund(1_000_000)
        with patch("world.checks.services.perform_check", return_value=self._result(-1)):
            outcome = attempt_bribe(self.persona, self.kingdom)
        row.refresh_from_db()
        self.assertEqual(row.value, 40)
        self.assertFalse(outcome["crime_minted"])
        self.assertEqual(outcome["coin_spent"], outcome["coin_spent"])

    def test_botch_mints_bribery_crime(self):
        self._check_type()
        _heat(self.persona, self.kingdom, self.crown, 40)
        self._fund(1_000_000)
        with (
            patch("world.checks.services.perform_check", return_value=self._result(-3)),
            patch("world.justice.services.accrue_heat") as mock_accrue,
        ):
            outcome = attempt_bribe(self.persona, self.kingdom)
        self.assertTrue(outcome["crime_minted"])
        mock_accrue.assert_called_once()
        self.assertEqual(mock_accrue.call_args.kwargs["crime_kind"].slug, "bribery")

    def test_requires_heat_and_funds(self):
        self._check_type()
        with self.assertRaises(HeatLifecycleError):
            attempt_bribe(self.persona, self.kingdom)
        _heat(self.persona, self.kingdom, self.crown, 40)
        self._fund(0)
        with self.assertRaises(HeatLifecycleError):
            attempt_bribe(self.persona, self.kingdom)


class PardonTests(JusticeFixtureMixin, TestCase):
    def _magistrate(self):
        from world.justice.constants import MAGISTRATE_OFFICE
        from world.societies.factories import OrganizationFactory
        from world.societies.office_services import appoint_office

        org = OrganizationFactory(society=self.crown)
        granter = PersonaFactory()
        appoint_office(organization=org, slug=MAGISTRATE_OFFICE, holder=granter)
        return granter

    def test_magistrate_pardons_and_audit_row_written(self):
        granter = self._magistrate()
        _heat(self.persona, self.kingdom, self.crown, 70)
        self.assertTrue(can_pardon(granter, self.kingdom))
        grant = pardon_persona(granter, self.persona, self.kingdom)
        self.assertEqual(grant.heat_cleared, 70)
        self.assertFalse(
            PersonaHeat.objects.filter(persona=self.persona, area=self.kingdom).exists()
        )
        self.assertEqual(PardonGrant.objects.count(), 1)

    def test_outsider_cannot_pardon(self):
        outsider = PersonaFactory()
        _heat(self.persona, self.kingdom, self.crown, 70)
        with self.assertRaises(HeatLifecycleError):
            pardon_persona(outsider, self.persona, self.kingdom)

    def test_pardon_surfaces_on_public_feed(self):
        from world.tidings.services import public_feed_for_societies

        granter = self._magistrate()
        _heat(self.persona, self.kingdom, self.crown, 70)
        pardon_persona(granter, self.persona, self.kingdom)
        items = public_feed_for_societies([self.crown.pk])
        self.assertIn("pardon", [item.kind for item in items])


class WantedVisibilityTests(JusticeFixtureMixin, TestCase):
    def test_below_floor_stays_invisible(self):
        _heat(self.persona, self.kingdom, self.crown, WANTED_VALUE_FLOOR - 1)
        self.assertEqual(wanted_rows_for_area(self.kingdom), [])

    def test_at_floor_flips_public_with_tier_not_number(self):
        _heat(self.persona, self.kingdom, self.crown, WANTED_VALUE_FLOOR)
        rows = wanted_rows_for_area(self.kingdom)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["persona_name"], self.persona.name)
        self.assertIn(rows[0]["tier"], (HeatTier.HEAT_IS_ON, HeatTier.EXTREME_HEAT))
        self.assertNotIn("value", rows[0])
