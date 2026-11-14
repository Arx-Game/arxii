"""The unsettled reading and the Mire share (#5123).

A character is unsettled when an affinity other than their main one has grown past its
settled share by more than the tolerance (5 points, a step per 5 more). A Sineater's Mire
burden is read apart and has its own allowance (30 percent of their lifetime resonance).
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import IntegrityError, transaction
from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    ResonanceFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import Affinity, CharacterResonance
from world.magic.services.aura import recompute_aura
from world.magic.services.conversion import _convert_partial
from world.magic.services.drift import check_resonance_focus, drift_for, get_drift_config
from world.magic.services.resonance import grant_resonance
from world.magic.services.soul_tether import _grant_sineating_resonance


def _hold(sheet, resonance, lifetime, mire=0):
    return CharacterResonance.objects.create(
        character_sheet=sheet,
        resonance=resonance,
        balance=lifetime,
        lifetime_earned=lifetime,
        mire_lifetime=mire,
    )


class _UnsettledCase(EvenniaTestCase):
    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.dawnlight = ResonanceFactory(name="Unsettled Dawnlight", affinity=self.celestial)
        self.wild = ResonanceFactory(name="Unsettled Wild", affinity=self.primal)
        self.dread = ResonanceFactory(name="Unsettled Dread", affinity=self.abyssal)
        self.sheet = CharacterSheetFactory()

    def settle(self, sheet=None, *, celestial="0", primal="0", abyssal="0"):
        sheet = sheet or self.sheet
        aura = CharacterAuraFactory(character=sheet)
        set_aura_split(aura, celestial=celestial, primal=primal, abyssal=abyssal)
        return aura


class UnsettledReadingTests(_UnsettledCase):
    def test_settled_mixed_character_not_unsettled(self) -> None:
        self.settle(celestial="70", abyssal="30")
        _hold(self.sheet, self.dawnlight, 70)
        _hold(self.sheet, self.dread, 30)

        reading = drift_for(self.sheet)

        self.assertEqual(reading.steps_past, 0)
        self.assertEqual(reading.main_affinity, self.celestial)
        self.assertIsNone(reading.leading_excess_resonance)

    def test_growth_in_main_never_unsettles(self) -> None:
        self.settle(celestial="90", abyssal="10")
        _hold(self.sheet, self.dawnlight, 80)
        _hold(self.sheet, self.dread, 20)
        self.assertEqual(drift_for(self.sheet).steps_past, 1)

        grant_resonance(self.sheet, self.dawnlight, 400, source=GainSource.STAFF_GRANT)

        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_minor_past_line_unsettles_and_names_resonance(self) -> None:
        self.settle(celestial="90", abyssal="10")
        _hold(self.sheet, self.dawnlight, 70)
        _hold(self.sheet, self.dread, 30)

        reading = drift_for(self.sheet)

        # 30 own share - 10 settled - 5 tolerance = 15 past, 5 to a step.
        self.assertEqual(reading.own_shares[self.abyssal.pk], Decimal(30))
        self.assertEqual(reading.settled_shares[self.abyssal.pk], Decimal(10))
        self.assertEqual(reading.excess_percent, Decimal(15))
        self.assertEqual(reading.steps_past, 3)
        self.assertEqual(reading.leading_excess_resonance, self.dread)

    def test_on_the_tolerance_is_not_past_it(self) -> None:
        self.settle(celestial="90", abyssal="10")
        _hold(self.sheet, self.dawnlight, 85)
        _hold(self.sheet, self.dread, 15)

        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_faded_streak_returns_without_unsettling(self) -> None:
        self.settle(celestial="70", abyssal="30")
        _hold(self.sheet, self.dawnlight, 95)
        dread_row = _hold(self.sheet, self.dread, 5)
        self.assertEqual(drift_for(self.sheet).steps_past, 0)

        # The streak grows back, up to the line it was settled at.
        dread_row.lifetime_earned = 40
        dread_row.save()

        self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_the_settled_line_survives_a_streak_with_nothing_left(self) -> None:
        aura = self.settle(celestial="70", abyssal="30")
        _hold(self.sheet, self.dawnlight, 100)
        dread_row = _hold(self.sheet, self.dread, 5)
        dread_row.delete()

        recompute_aura(self.sheet)

        aura.__dict__.pop("cached_shares", None)
        share = aura.shares.get(affinity=self.abyssal)
        self.assertEqual(share.percent, Decimal(0))
        self.assertEqual(share.settled_percent, Decimal(30))

    def test_streak_overtaking_main_still_unsettled(self) -> None:
        self.settle(celestial="80", abyssal="20")
        _hold(self.sheet, self.dawnlight, 10)
        _hold(self.sheet, self.dread, 90)

        reading = drift_for(self.sheet)

        # The main affinity is who they are, not what is largest now: Celestial still.
        self.assertEqual(reading.main_affinity, self.celestial)
        self.assertEqual(reading.steps_past, 13)  # ceil((90 - 20 - 5) / 5)
        self.assertEqual(reading.leading_excess_resonance, self.dread)

    def test_the_rule_runs_both_ways(self) -> None:
        self.settle(abyssal="90", celestial="10")
        _hold(self.sheet, self.dread, 70)
        _hold(self.sheet, self.dawnlight, 30)

        reading = drift_for(self.sheet)

        self.assertEqual(reading.main_affinity, self.abyssal)
        self.assertEqual(reading.steps_past, 3)
        self.assertEqual(reading.leading_excess_resonance, self.dawnlight)

    def test_a_worn_alternate_self_does_not_change_who_they_are(self) -> None:
        self.settle(celestial="100")
        _hold(self.sheet, self.dawnlight, 100)

        with patch(
            "world.magic.services.acting_aura.acting_aura",
            side_effect=AssertionError("the reading never asks for the acting aura"),
        ):
            self.assertEqual(drift_for(self.sheet).steps_past, 0)

    def test_no_aura_and_nothing_settled_read_zero(self) -> None:
        _hold(self.sheet, self.dread, 500)
        self.assertEqual(drift_for(self.sheet).steps_past, 0)
        self.assertIsNone(drift_for(self.sheet).main_affinity)

        bare = CharacterSheetFactory()
        aura = CharacterAuraFactory(character=bare)
        for share in list(aura.cached_shares):
            share.settled_percent = Decimal(0)
            share.save()
        _hold(bare, self.dread, 500)
        self.assertEqual(drift_for(bare).steps_past, 0)


class MireShareTests(_UnsettledCase):
    def test_sineater_mire_within_allowance_not_unsettled(self) -> None:
        self.settle(celestial="100")
        _hold(self.sheet, self.dawnlight, 100)
        _hold(self.sheet, self.dread, 30, mire=30)

        reading = drift_for(self.sheet)

        # 30 of 130 is under the 30 percent allowance, and none of it is their own.
        self.assertEqual(reading.steps_past, 0)
        self.assertEqual(reading.own_shares.get(self.abyssal.pk, Decimal(0)), Decimal(0))
        self.assertAlmostEqual(reading.mire_share_percent, Decimal(30) / 130 * 100, places=6)

    def test_sineater_mire_past_allowance_unsettles(self) -> None:
        self.settle(celestial="100")
        _hold(self.sheet, self.dawnlight, 100)
        _hold(self.sheet, self.dread, 60, mire=60)

        reading = drift_for(self.sheet)

        # 60 of 160 is 37.5 percent: 7.5 past the allowance, two steps of five.
        self.assertEqual(reading.mire_share_percent, Decimal("37.5"))
        self.assertEqual(reading.excess_percent, Decimal("7.5"))
        self.assertEqual(reading.steps_past, 2)
        self.assertEqual(reading.leading_excess_resonance, self.dread)

    def test_sinner_sineating_gain_counts_as_own(self) -> None:
        sineater = CharacterSheetFactory()
        self.settle(self.sheet, primal="100")
        self.settle(sineater, celestial="100")
        _hold(self.sheet, self.wild, 75)
        _hold(sineater, self.dawnlight, 75)

        offer = SimpleNamespace(
            sinner_sheet=self.sheet, sineater_sheet=sineater, resonance=self.dread
        )
        _grant_sineating_resonance(offer, 25)

        sinner_row = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.dread
        )
        sineater_row = CharacterResonance.objects.get(
            character_sheet=sineater, resonance=self.dread
        )
        self.assertEqual(sinner_row.mire_lifetime, 0)
        self.assertEqual(sineater_row.mire_lifetime, 25)
        # The Sinner's 25 is their own Abyssal: 25 percent past a line of 0, less 5.
        self.assertEqual(drift_for(self.sheet).steps_past, 4)
        # The Sineater's 25 is the Mire's: 25 percent, under the allowance.
        self.assertEqual(drift_for(sineater).steps_past, 0)


class FocusCheckTests(_UnsettledCase):
    def setUp(self) -> None:
        super().setUp()
        cfg = get_drift_config()
        cfg.focus_check_type = CheckTypeFactory(name="Unsettled Focus")
        cfg.conflict_condition = ConditionTemplateFactory(name="Unsettled Conflict")
        cfg.save()
        self.character = self.sheet.character

    def test_off_main_pull_adds_no_focus_steps(self) -> None:
        self.settle(celestial="100")
        _hold(self.sheet, self.dawnlight, 100)

        with patch("world.checks.services.perform_check_with_modifiers") as roll:
            outcome = check_resonance_focus(self.character, Mock())

        # Settled: nothing to roll. A pull no longer reaches this check at all.
        self.assertIsNone(outcome)
        roll.assert_not_called()
        with self.assertRaises(TypeError):
            check_resonance_focus(self.character, Mock(), pulled_resonances=(self.dread,))

    def test_focus_message_uses_unsettled_wording(self) -> None:
        self.settle(celestial="90", abyssal="10")
        _hold(self.sheet, self.dawnlight, 70)
        _hold(self.sheet, self.dread, 30)

        with (
            patch(
                "world.checks.services.perform_check_with_modifiers",
                return_value=Mock(success_level=1),
            ) as roll,
            patch.object(self.character, "msg") as msg,
        ):
            outcome = check_resonance_focus(self.character, Mock())

        self.assertEqual(outcome.steps, 3)
        # Difficulty: 10 base + 3 steps of 2.
        self.assertEqual(roll.call_args.args[2], 16)
        told = " ".join(call.args[0] for call in msg.call_args_list)
        self.assertIn("Your Unsettled Dread has grown strong enough to make you unsettled", told)
        self.assertNotIn("drift", told)


class MovePartialMireTests(_UnsettledCase):
    def test_move_partial_moves_mire_proportionally(self) -> None:
        source = _hold(self.sheet, self.dread, 100, mire=40)

        _convert_partial(source, self.sheet, self.dawnlight, Decimal(1), 50)

        source.refresh_from_db()
        self.assertEqual(source.lifetime_earned, 50)
        self.assertEqual(source.mire_lifetime, 20)
        target = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.dawnlight
        )
        self.assertEqual(target.mire_lifetime, 0)

    def test_mire_never_exceeds_lifetime_after_rounding(self) -> None:
        source = CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.dread,
            balance=3,
            lifetime_earned=10,
            mire_lifetime=9,
        )

        _convert_partial(source, self.sheet, self.dawnlight, Decimal(1), 2)

        source.refresh_from_db()
        self.assertLessEqual(source.mire_lifetime, source.lifetime_earned)

    def test_the_database_refuses_mire_past_lifetime(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterResonance.objects.create(
                character_sheet=self.sheet,
                resonance=self.dread,
                balance=0,
                lifetime_earned=5,
                mire_lifetime=6,
            )
