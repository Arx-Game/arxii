"""Journeys for digging deep (#4738, slice 2 of #4727).

Mira and Tomas are played fighters in one escalating encounter in "The Road". Staff have
authored a Dug deep surge tuning (a Resolve check against a difficulty, a Partial band of 2
and a Success band of 5) and the strain config's fatigue cost. Mira digs deep with
``combat digdeep`` (or the web action): she rolls, her intensity rises by the outcome's band,
and she pays mental fatigue unless she holds a free dig deep. Tomas's Rally of Mira grants one.

Rolls are forced with ``force_check_outcome`` so each outcome is the test's choice.
"""

from __future__ import annotations

from unittest.mock import patch

from integration_tests.test_surge_rolls_journeys import _SurgeField
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SocialManeuverConfigFactory, SurgeDegreeBandFactory
from world.combat.models import StrainConfig, SurgeTuning
from world.conditions.factories import ConditionTemplateFactory
from world.fatigue.services import get_or_create_fatigue_pool
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory

PARTIAL_DIG_DEEP = 2
SUCCESS_DIG_DEEP = 5
DIG_DEEP_DIFFICULTY = 10
FATIGUE_COST = 3
ALREADY = "You have already dug deep this round."


class _DigDeepField(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        StrainConfig.objects.update_or_create(
            pk=1,
            defaults={"dig_deep_fatigue_cost": FATIGUE_COST, "free_dig_deeps_per_encouragement": 1},
        )
        self.author_tuning(
            SurgeTriggerKind.DUG_DEEP,
            "Resolve",
            partial=PARTIAL_DIG_DEEP,
            success=SUCCESS_DIG_DEEP,
            potency_base=DIG_DEEP_DIFFICULTY,
        )

    def dig_deep(self, outcome) -> str:
        """Mira types ``combat digdeep`` with her roll forced to ``outcome``."""
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(outcome):
            return self.telnet(self.mira, "combat digdeep")

    def close_round(self) -> None:
        """End this round and open the next, as the round loop does."""
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save()
        self.next_round()

    def mental_fatigue(self) -> int:
        return get_or_create_fatigue_pool(self.mira.sheet_data).mental_current

    def free_dig_deeps(self, character) -> int:
        return CharacterEngagement.objects.get(character=character.sheet_data).free_dig_deeps


class DiggingDeep(_DigDeepField):
    def test_a_success_surges_by_the_success_band_and_costs_fatigue(self) -> None:
        told = self.dig_deep(self.success)

        self.assertIn("You dig deep.", told)
        self.assertIn("Cost: mental fatigue 3.", told)
        self.assertEqual(self.intensity(self.mira), SUCCESS_DIG_DEEP)
        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertTold(
            self.mira,
            f"Resolve check vs resolve difficulty {DIG_DEEP_DIFFICULTY} · Success "
            f"· Intensity +{SUCCESS_DIG_DEEP}",
        )
        record = self.records(SurgeTriggerKind.DUG_DEEP).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.potency, DIG_DEEP_DIFFICULTY)
        self.assertNotTold(self.tomas, "Resolve check")

    def test_a_better_roll_never_surges_less(self) -> None:
        self.dig_deep(self.partial)
        partial_gain = self.intensity(self.mira)
        self.close_round()
        self.dig_deep(self.success)

        self.assertEqual(partial_gain, PARTIAL_DIG_DEEP)
        self.assertGreater(self.intensity(self.mira) - partial_gain, partial_gain)

    def test_a_second_dig_deep_the_same_round_is_refused_and_costs_nothing(self) -> None:
        self.dig_deep(self.success)
        fatigue = self.mental_fatigue()

        told = self.dig_deep(self.success)

        self.assertIn(ALREADY, told)
        self.assertEqual(self.mental_fatigue(), fatigue)
        self.assertEqual(self.intensity(self.mira), SUCCESS_DIG_DEEP)

    def test_the_next_round_she_can_dig_deep_again(self) -> None:
        self.dig_deep(self.success)
        self.close_round()

        self.dig_deep(self.success)

        self.assertEqual(self.intensity(self.mira), 2 * SUCCESS_DIG_DEEP)
        self.assertEqual(self.mental_fatigue(), 2 * FATIGUE_COST)

    def test_the_configured_pool_and_amount_are_charged(self) -> None:
        StrainConfig.objects.update_or_create(
            pk=1, defaults={"dig_deep_fatigue_category": "social", "dig_deep_fatigue_cost": 4}
        )
        self.dig_deep(self.partial)

        pool = get_or_create_fatigue_pool(self.mira.sheet_data)
        self.assertEqual((pool.social_current, pool.mental_current), (4, 0))

    def test_digging_deep_from_the_web_does_the_same(self) -> None:
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            result = self.web(self.mira, "combat_dig_deep")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.intensity(self.mira), SUCCESS_DIG_DEEP)

    def test_the_encounter_endpoint_digs_deep_and_says_what_a_dig_deep_costs(self) -> None:
        client = self.api(self.account_of(self.mira))
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            response = client.post(f"/api/combat/{self.encounter.pk}/dig-deep/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.intensity(self.mira), SUCCESS_DIG_DEEP)
        seats = {p["id"]: p for p in response.json()["participants"]}
        self.assertEqual(
            seats[self.mira_seat.pk]["dig_deep"],
            {
                "free_dig_deeps": 0,
                "fatigue_category": "mental",
                "fatigue_cost": FATIGUE_COST,
                "dug_deep_this_round": True,
                "given_by": None,
            },
        )
        self.assertIsNone(seats[self.tomas_seat.pk]["dig_deep"])

        again = client.post(f"/api/combat/{self.encounter.pk}/dig-deep/")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["detail"], ALREADY)


class AFailedDigDeep(_DigDeepField):
    """A Failure band that gives nothing writes no surge record, yet the round is spent."""

    def setUp(self) -> None:
        super().setUp()
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        SurgeDegreeBandFactory(
            tuning=SurgeTuning.objects.get(trigger_kind=SurgeTriggerKind.DUG_DEEP),
            outcome=self.failure,
            intensity=0,
        )

    def test_the_zero_band_reads_plainly(self) -> None:
        self.assertIn("The roll gave no surge.", self.dig_deep(self.failure))

    def test_a_failure_costs_fatigue_and_cannot_be_rerolled_the_same_round(self) -> None:
        self.dig_deep(self.failure)

        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertEqual(self.intensity(self.mira), 0)
        self.assertFalse(self.records(SurgeTriggerKind.DUG_DEEP).exists())

        told = self.dig_deep(self.success)

        self.assertIn(ALREADY, told)
        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertEqual(self.intensity(self.mira), 0)

    def test_the_next_round_she_may_try_again(self) -> None:
        self.dig_deep(self.failure)
        self.close_round()

        self.dig_deep(self.success)

        self.assertEqual(self.intensity(self.mira), SUCCESS_DIG_DEEP)


class BeingEncouraged(_DigDeepField):
    def setUp(self) -> None:
        super().setUp()
        # Staff designate Rally's success condition; its name does not matter (#4739).
        SocialManeuverConfigFactory(
            rally_success_condition=ConditionTemplateFactory(name="Heartened")
        )
        self.author_tuning(SurgeTriggerKind.RALLIED, "Rally", partial=1, success=1)

    def test_a_successful_rally_grants_a_free_dig_deep_that_costs_no_fatigue(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)

        self.assertEqual(self.free_dig_deeps(self.mira), 1)
        self.assertTold(self.mira, "gives you a free dig deep")

        self.close_round()
        told = self.dig_deep(self.success)

        self.assertIn("Cost: a free dig deep.", told)
        self.assertEqual(self.free_dig_deeps(self.mira), 0)
        self.assertEqual(self.mental_fatigue(), 0)

    def _mira_s_offer(self, viewer) -> dict | None:
        body = self.api(self.account_of(viewer)).get(f"/api/combat/{self.encounter.pk}/").json()
        return {p["id"]: p for p in body["participants"]}[self.mira_seat.pk]["dig_deep"]

    def test_the_payload_credits_the_rallier_until_the_last_free_dig_deep_is_spent(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)

        offer = self._mira_s_offer(self.mira)
        self.assertEqual((offer["free_dig_deeps"], offer["given_by"]), (1, "Tomas"))
        self.assertIsNone(self._mira_s_offer(self.tomas))
        self.assertEqual(self.free_dig_deeps(self.tomas), 0)

        self.close_round()
        self.dig_deep(self.success)

        offer = self._mira_s_offer(self.mira)
        self.assertEqual((offer["free_dig_deeps"], offer["given_by"]), (0, None))
        self.assertIsNone(
            CharacterEngagement.objects.get(character=self.mira.sheet_data).free_dig_deeps_given_by
        )

    def test_the_free_dig_deep_is_spent_once_then_fatigue_returns(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)
        self.close_round()
        self.dig_deep(self.success)
        self.close_round()

        self.dig_deep(self.success)

        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)

    def test_a_failed_rally_grants_none(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.partial)

        self.assertEqual(self.free_dig_deeps(self.mira), 0)


class DiggingDeepWhereYouCannot(_DigDeepField):
    def test_outside_a_fight_it_refuses(self) -> None:
        told = self.telnet(self.make_player("Odo", room=self.road), "combat digdeep")

        self.assertIn("You are not in an active combat round.", told)

    def test_without_an_authored_tuning_it_refuses_and_spends_nothing(self) -> None:
        from world.combat.models import SurgeTuning

        SurgeTuning.objects.filter(trigger_kind=SurgeTriggerKind.DUG_DEEP).delete()

        told = self.dig_deep(self.success)

        self.assertIn("There is nothing to dig deep with yet.", told)
        self.assertEqual(self.mental_fatigue(), 0)
        self.assertEqual(self.intensity(self.mira), 0)


class ARoundThatRollsBack(BeingEncouraged):
    def test_a_rolled_back_round_leaves_no_free_dig_deep_to_see_or_spend(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        with (
            patch(
                "world.combat.services.declarations.rally._surge_rallied_ally",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.resolve(self.success)

        self.assertEqual(self.free_dig_deeps(self.mira), 0)
        self.assertEqual(self._mira_s_offer(self.mira)["free_dig_deeps"], 0)
        self.assertIsNone(self._mira_s_offer(self.mira)["given_by"])
        self.assertNotTold(self.mira, "free dig deep")


class AFailedDigDeepWrite(_DigDeepField):
    def test_a_dig_deep_that_fails_midway_leaves_the_cached_rows_as_the_database_has_them(
        self,
    ) -> None:
        with (
            patch("world.combat.dig_deep.apply_rolled_surge", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
            force_check_outcome(self.success),
        ):
            self.telnet(self.mira, "combat digdeep")

        engagement = CharacterEngagement.objects.get(character=self.mira.sheet_data)
        stored = CharacterEngagement.objects.filter(pk=engagement.pk).values(
            "last_dug_deep_round", "intensity_modifier", "control_modifier"
        )[0]
        self.assertIsNone(stored["last_dug_deep_round"])
        self.assertEqual(engagement.last_dug_deep_round, stored["last_dug_deep_round"])
        self.assertEqual(engagement.intensity_modifier, stored["intensity_modifier"])
        self.assertEqual(self.mental_fatigue(), 0)
        # And she may dig deep afterwards: nothing was spent.
        self.dig_deep(self.success)
        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
