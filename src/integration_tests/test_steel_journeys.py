"""Journeys for steeling yourself (#4738, slice 2 of #4727).

Mira and Tomas are played fighters in one escalating encounter in "The Road". Staff have
authored a Steeled surge tuning (a Resolve check against a difficulty, a Partial band of 2
and a Success band of 5) and the strain config's fatigue cost. Mira steels herself with
``combat steel`` (or the web action): she rolls, her intensity rises by the outcome's band,
and she pays mental fatigue unless she holds a free steel. Tomas's Rally of Mira grants one.

Rolls are forced with ``force_check_outcome`` so each outcome is the test's choice.
"""

from __future__ import annotations

from integration_tests.test_surge_rolls_journeys import _SurgeField
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SurgeDegreeBandFactory
from world.combat.models import StrainConfig, SurgeTuning
from world.combat.social_combat_content import INSPIRED_CONDITION_NAME
from world.conditions.factories import ConditionTemplateFactory
from world.fatigue.services import get_or_create_fatigue_pool
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory

PARTIAL_STEEL = 2
SUCCESS_STEEL = 5
STEEL_DIFFICULTY = 10
FATIGUE_COST = 3
ALREADY = "You have already steeled yourself this round."


class _SteelField(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        StrainConfig.objects.update_or_create(
            pk=1, defaults={"steel_fatigue_cost": FATIGUE_COST, "free_steels_per_encouragement": 1}
        )
        self.author_tuning(
            SurgeTriggerKind.STEELED,
            "Resolve",
            partial=PARTIAL_STEEL,
            success=SUCCESS_STEEL,
            potency_base=STEEL_DIFFICULTY,
        )

    def steel(self, outcome) -> str:
        """Mira types ``combat steel`` with her roll forced to ``outcome``."""
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(outcome):
            return self.telnet(self.mira, "combat steel")

    def close_round(self) -> None:
        """End this round and open the next, as the round loop does."""
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save()
        self.next_round()

    def mental_fatigue(self) -> int:
        return get_or_create_fatigue_pool(self.mira.sheet_data).mental_current

    def free_steels(self, character) -> int:
        return CharacterEngagement.objects.get(character=character.sheet_data).free_steels


class SteelingYourself(_SteelField):
    def test_a_success_surges_by_the_success_band_and_costs_fatigue(self) -> None:
        told = self.steel(self.success)

        self.assertIn("You steel yourself.", told)
        self.assertEqual(self.intensity(self.mira), SUCCESS_STEEL)
        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertTold(
            self.mira,
            f"Resolve check vs resolve difficulty {STEEL_DIFFICULTY} · Success "
            f"· Intensity +{SUCCESS_STEEL}",
        )
        record = self.records(SurgeTriggerKind.STEELED).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.potency, STEEL_DIFFICULTY)
        self.assertNotTold(self.tomas, "Resolve check")

    def test_a_better_roll_never_surges_less(self) -> None:
        self.steel(self.partial)
        partial_gain = self.intensity(self.mira)
        self.close_round()
        self.steel(self.success)

        self.assertEqual(partial_gain, PARTIAL_STEEL)
        self.assertGreater(self.intensity(self.mira) - partial_gain, partial_gain)

    def test_a_second_steel_the_same_round_is_refused_and_costs_nothing(self) -> None:
        self.steel(self.success)
        fatigue = self.mental_fatigue()

        told = self.steel(self.success)

        self.assertIn(ALREADY, told)
        self.assertEqual(self.mental_fatigue(), fatigue)
        self.assertEqual(self.intensity(self.mira), SUCCESS_STEEL)

    def test_the_next_round_she_can_steel_again(self) -> None:
        self.steel(self.success)
        self.close_round()

        self.steel(self.success)

        self.assertEqual(self.intensity(self.mira), 2 * SUCCESS_STEEL)
        self.assertEqual(self.mental_fatigue(), 2 * FATIGUE_COST)

    def test_the_configured_pool_and_amount_are_charged(self) -> None:
        StrainConfig.objects.update_or_create(
            pk=1, defaults={"steel_fatigue_category": "social", "steel_fatigue_cost": 4}
        )
        self.steel(self.partial)

        pool = get_or_create_fatigue_pool(self.mira.sheet_data)
        self.assertEqual((pool.social_current, pool.mental_current), (4, 0))

    def test_steeling_from_the_web_does_the_same(self) -> None:
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            result = self.web(self.mira, "combat_steel")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.intensity(self.mira), SUCCESS_STEEL)

    def test_the_encounter_endpoint_steels_and_says_what_a_steel_costs(self) -> None:
        client = self.api(self.account_of(self.mira))
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            response = client.post(f"/api/combat/{self.encounter.pk}/steel/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.intensity(self.mira), SUCCESS_STEEL)
        seats = {p["id"]: p for p in response.json()["participants"]}
        self.assertEqual(
            seats[self.mira_seat.pk]["steel"],
            {
                "free_steels": 0,
                "fatigue_category": "mental",
                "fatigue_cost": FATIGUE_COST,
                "given_by": None,
            },
        )
        self.assertIsNone(seats[self.tomas_seat.pk]["steel"])

        again = client.post(f"/api/combat/{self.encounter.pk}/steel/")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["detail"], ALREADY)


class AFailedSteel(_SteelField):
    """A Failure band that gives nothing writes no surge record, yet the round is spent."""

    def setUp(self) -> None:
        super().setUp()
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        SurgeDegreeBandFactory(
            tuning=SurgeTuning.objects.get(trigger_kind=SurgeTriggerKind.STEELED),
            outcome=self.failure,
            intensity=0,
        )

    def test_a_failure_costs_fatigue_and_cannot_be_rerolled_the_same_round(self) -> None:
        self.steel(self.failure)

        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertEqual(self.intensity(self.mira), 0)
        self.assertFalse(self.records(SurgeTriggerKind.STEELED).exists())

        told = self.steel(self.success)

        self.assertIn(ALREADY, told)
        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)
        self.assertEqual(self.intensity(self.mira), 0)

    def test_the_next_round_she_may_try_again(self) -> None:
        self.steel(self.failure)
        self.close_round()

        self.steel(self.success)

        self.assertEqual(self.intensity(self.mira), SUCCESS_STEEL)


class BeingEncouraged(_SteelField):
    def setUp(self) -> None:
        super().setUp()
        ConditionTemplateFactory(name=INSPIRED_CONDITION_NAME)
        self.author_tuning(SurgeTriggerKind.RALLIED, "Rally", partial=1, success=1)

    def test_a_successful_rally_grants_a_free_steel_that_costs_no_fatigue(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)

        self.assertEqual(self.free_steels(self.mira), 1)
        self.assertTold(self.mira, "gives you a free steel")

        self.close_round()
        told = self.steel(self.success)

        self.assertIn("Cost: a free steel.", told)
        self.assertEqual(self.free_steels(self.mira), 0)
        self.assertEqual(self.mental_fatigue(), 0)

    def _mira_s_offer(self, viewer) -> dict | None:
        body = self.api(self.account_of(viewer)).get(f"/api/combat/{self.encounter.pk}/").json()
        return {p["id"]: p for p in body["participants"]}[self.mira_seat.pk]["steel"]

    def test_the_payload_credits_the_rallier_until_the_last_free_steel_is_spent(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)

        offer = self._mira_s_offer(self.mira)
        self.assertEqual((offer["free_steels"], offer["given_by"]), (1, "Tomas"))
        self.assertIsNone(self._mira_s_offer(self.tomas))

        self.close_round()
        self.steel(self.success)

        offer = self._mira_s_offer(self.mira)
        self.assertEqual((offer["free_steels"], offer["given_by"]), (0, None))
        self.assertIsNone(
            CharacterEngagement.objects.get(character=self.mira.sheet_data).free_steels_given_by
        )

    def test_the_free_steel_is_spent_once_then_fatigue_returns(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.success)
        self.close_round()
        self.steel(self.success)
        self.close_round()

        self.steel(self.success)

        self.assertEqual(self.mental_fatigue(), FATIGUE_COST)

    def test_a_failed_rally_grants_none(self) -> None:
        self.telnet(self.tomas, "combat rally Mira")
        self.resolve(self.partial)

        self.assertEqual(self.free_steels(self.mira), 0)


class SteelingWhereYouCannot(_SteelField):
    def test_outside_a_fight_it_refuses(self) -> None:
        told = self.telnet(self.make_player("Odo", room=self.road), "combat steel")

        self.assertIn("You are not in an active combat round.", told)

    def test_without_an_authored_tuning_it_refuses_and_spends_nothing(self) -> None:
        from world.combat.models import SurgeTuning

        SurgeTuning.objects.filter(trigger_kind=SurgeTriggerKind.STEELED).delete()

        told = self.steel(self.success)

        self.assertIn("There is nothing to steel yourself with yet.", told)
        self.assertEqual(self.mental_fatigue(), 0)
        self.assertEqual(self.intensity(self.mira), 0)
