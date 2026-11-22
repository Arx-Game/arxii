"""Journeys for attuning an anima ritual (#5280).

Mara's ritual already carries a Primal pick (Hollow) and an outward pick (Ruin, Abyssal): her
first setup was free, so the picks are locked. To change them she attunes the ritual, by telnet
(``ritual attune primal=<name|none> outward=<name|none>``) or the web (``POST
/api/magic/anima-ritual/attune/``); both converge on ``AttuneAnimaRitualAction``.

Staff set the attunement's price on ``AnimaConfig``: 2 anima, 5 resonance in each newly picked
resonance, 10 action points, and a check at level 1 difficulty. Numbers are worked out by hand.
Mara starts with 10 anima, 100 action points and 20 balance in each of Hollow, Ruin, Marrow
(Primal) and Dawn (Celestial). A paid attunement to Marrow and Dawn leaves her 8 anima, 90 action
points, 15 Marrow and 15 Dawn, and Hollow and Ruin untouched at 20. A roll that fails spends the
same and leaves the picks as they were.
"""

from __future__ import annotations

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.action_points.factories import ActionPointPoolFactory
from world.action_points.models import ActionPointPool
from world.checks.factories import CheckTypeFactory
from world.checks.services import difficulty_points
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    ensure_conversion_pairs,
)
from world.magic.models import AnimaConfig, CharacterAnima, CharacterResonance, RitualCheckConfig
from world.traits.factories import ensure_level_ladder
from world.traits.services import ensure_canonical_check_outcome

ATTUNE = "/api/magic/anima-ritual/attune/"
ANIMA_COST, RESONANCE_COST, AP_COST = 2, 5, 10
STARTING_ANIMA, STARTING_AP, STARTING_BALANCE = 10, 100, 20
KEPT = "Your attunement did not take hold. Your ritual keeps the resonances it had."


class _MarasRitual(JourneyCase):
    """Mara, her locked picks (Hollow and Ruin) and the price of attuning to Marrow and Dawn."""

    def setUp(self) -> None:
        super().setUp()
        ensure_level_ladder()
        celestial, primal, abyssal = ensure_conversion_pairs()
        self.hollow = ResonanceFactory(name="Hollow", affinity=primal)
        self.marrow = ResonanceFactory(name="Marrow", affinity=primal)
        self.ruin = ResonanceFactory(name="Ruin", affinity=abyssal)
        self.dawn = ResonanceFactory(name="Dawn", affinity=celestial)
        room = self.make_room("The Lantern")
        self.mara = self.make_player("Mara", room=room)
        sheet = self.mara.sheet_data
        CharacterAuraFactory(character=sheet)
        CharacterAnimaFactory(character=sheet, current=STARTING_ANIMA, maximum=STARTING_ANIMA)
        ActionPointPoolFactory(character=sheet, current=STARTING_AP, maximum=200)
        for held in (self.hollow, self.marrow, self.ruin, self.dawn):
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=held, balance=STARTING_BALANCE
            )
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=self.account_of(self.mara),
            hedge_accessible=True,
        )
        RitualCheckConfigFactory(
            ritual=ritual, primal_resonance=self.hollow, outward_resonance=self.ruin
        )
        self.ritual = ritual
        self.attunement_check = CheckTypeFactory()
        config = AnimaConfig.get_singleton()
        config.attunement_anima_cost = ANIMA_COST
        config.attunement_resonance_cost = RESONANCE_COST
        config.attunement_ap_cost = AP_COST
        config.attunement_check_type = self.attunement_check
        config.attunement_difficulty_level = 1
        config.save()
        self.success = ensure_canonical_check_outcome("Success")
        self.failure = ensure_canonical_check_outcome("Failure")

    def picks(self) -> tuple[int | None, int | None]:
        return RitualCheckConfig.objects.values_list(
            "primal_resonance_id", "outward_resonance_id"
        ).get(ritual=self.ritual)

    def balance(self, resonance) -> int:
        return CharacterResonance.objects.values_list("balance", flat=True).get(
            character_sheet=self.mara.sheet_data, resonance=resonance
        )

    def anima(self) -> int:
        return CharacterAnima.objects.values_list("current", flat=True).get(
            character=self.mara.sheet_data
        )

    def action_points(self) -> int:
        return ActionPointPool.objects.values_list("current", flat=True).get(
            character=self.mara.sheet_data
        )

    def assert_nothing_spent(self) -> None:
        self.assertEqual(self.anima(), STARTING_ANIMA)
        self.assertEqual(self.action_points(), STARTING_AP)
        for held in (self.hollow, self.marrow, self.ruin, self.dawn):
            self.assertEqual(self.balance(held), STARTING_BALANCE)
        self.assertEqual(self.picks(), (self.hollow.pk, self.ruin.pk))


class AttuningByTelnet(_MarasRitual):
    def test_a_paid_attunement_changes_both_picks(self) -> None:
        with force_check_outcome(self.success) as capture:
            told = self.telnet(self.mara, "ritual attune primal=Marrow outward=Dawn")

        self.assertIn("Your ritual is now attuned to Marrow and Dawn.", told)
        self.assertEqual(capture.check_type, self.attunement_check)
        self.assertEqual(capture.target_difficulty, difficulty_points(1))
        self.assertEqual(self.picks(), (self.marrow.pk, self.dawn.pk))
        self.assertEqual(self.anima(), STARTING_ANIMA - ANIMA_COST)
        self.assertEqual(self.action_points(), STARTING_AP - AP_COST)
        self.assertEqual(self.balance(self.marrow), STARTING_BALANCE - RESONANCE_COST)
        self.assertEqual(self.balance(self.dawn), STARTING_BALANCE - RESONANCE_COST)
        self.assertEqual(self.balance(self.hollow), STARTING_BALANCE)
        self.assertEqual(self.balance(self.ruin), STARTING_BALANCE)

    def test_a_failed_roll_spends_everything_and_changes_nothing(self) -> None:
        with force_check_outcome(self.failure):
            told = self.telnet(self.mara, "ritual attune primal=Marrow outward=Dawn")

        self.assertIn(KEPT, told)
        self.assertEqual(self.picks(), (self.hollow.pk, self.ruin.pk))
        self.assertEqual(self.anima(), STARTING_ANIMA - ANIMA_COST)
        self.assertEqual(self.action_points(), STARTING_AP - AP_COST)
        self.assertEqual(self.balance(self.marrow), STARTING_BALANCE - RESONANCE_COST)
        self.assertEqual(self.balance(self.dawn), STARTING_BALANCE - RESONANCE_COST)

    def test_leaving_a_slot_empty_names_none(self) -> None:
        with force_check_outcome(self.success):
            told = self.telnet(self.mara, "ritual attune primal=Marrow outward=none")

        self.assertIn("Your ritual is now attuned to Marrow.", told)
        self.assertEqual(self.picks(), (self.marrow.pk, None))
        self.assertEqual(self.balance(self.marrow), STARTING_BALANCE - RESONANCE_COST)

    def test_the_same_picks_are_refused_and_cost_nothing(self) -> None:
        told = self.telnet(self.mara, "ritual attune primal=Hollow outward=Ruin")

        self.assertIn("Your ritual already carries those resonances.", told)
        self.assert_nothing_spent()

    def test_a_wrong_affinity_pick_is_refused_and_costs_nothing(self) -> None:
        told = self.telnet(self.mara, "ritual attune primal=Dawn outward=Ruin")

        self.assertIn("Dawn is not a Primal resonance.", told)
        self.assert_nothing_spent()

    def test_a_line_that_names_only_one_slot_gets_the_usage(self) -> None:
        told = self.telnet(self.mara, "ritual attune primal=Marrow")

        self.assertIn("Usage: ritual attune primal=<name|none> outward=<name|none>", told)
        self.assert_nothing_spent()

    def test_an_unknown_resonance_is_refused(self) -> None:
        told = self.telnet(self.mara, "ritual attune primal=Marrow outward=Nowhere")

        self.assertIn("There is no resonance called Nowhere.", told)
        self.assert_nothing_spent()

    def test_too_few_action_points_refuses_before_anything_is_spent(self) -> None:
        pool = ActionPointPool.objects.get(character=self.mara.sheet_data)
        pool.current = AP_COST - 1
        pool.save(update_fields=["current"])

        told = self.telnet(self.mara, "ritual attune primal=Marrow outward=Dawn")

        self.assertIn("You don't have enough action points for that.", told)
        self.assertEqual(self.action_points(), AP_COST - 1)
        self.assertEqual(self.anima(), STARTING_ANIMA)
        self.assertEqual(self.balance(self.marrow), STARTING_BALANCE)
        self.assertEqual(self.picks(), (self.hollow.pk, self.ruin.pk))


class AttuningOnTheWeb(_MarasRitual):
    def post(self, primal, outward, *, outcome=None):
        body = {
            "character_sheet_id": self.mara.sheet_data.pk,
            "primal_resonance_id": primal.pk if primal else None,
            "outward_resonance_id": outward.pk if outward else None,
        }
        client = self.api(self.account_of(self.mara))
        if outcome is None:
            return client.post(ATTUNE, body, format="json")
        with force_check_outcome(outcome):
            return client.post(ATTUNE, body, format="json")

    def test_a_paid_attunement_replies_with_the_new_choices(self) -> None:
        answer = self.post(self.marrow, self.dawn, outcome=self.success)

        self.assertEqual(answer.status_code, status.HTTP_200_OK, answer.content)
        body = answer.json()
        self.assertTrue(body["changed"])
        self.assertEqual(body["message"], "Your ritual is now attuned to Marrow and Dawn.")
        self.assertEqual(body["choices"]["primal_pick"]["id"], self.marrow.pk)
        self.assertEqual(body["choices"]["outward_pick"]["id"], self.dawn.pk)
        self.assertEqual(self.picks(), (self.marrow.pk, self.dawn.pk))
        self.assertEqual(self.anima(), STARTING_ANIMA - ANIMA_COST)
        self.assertEqual(self.action_points(), STARTING_AP - AP_COST)

    def test_a_failed_roll_is_a_200_that_says_nothing_changed(self) -> None:
        answer = self.post(self.marrow, self.dawn, outcome=self.failure)

        self.assertEqual(answer.status_code, status.HTTP_200_OK, answer.content)
        body = answer.json()
        self.assertFalse(body["changed"])
        self.assertEqual(body["message"], KEPT)
        self.assertEqual(body["choices"]["primal_pick"]["id"], self.hollow.pk)
        self.assertEqual(self.action_points(), STARTING_AP - AP_COST)
        self.assertEqual(self.picks(), (self.hollow.pk, self.ruin.pk))

    def test_a_refusal_is_a_400_and_spends_nothing(self) -> None:
        answer = self.post(self.hollow, self.ruin)

        self.assertEqual(answer.status_code, status.HTTP_400_BAD_REQUEST, answer.content)
        self.assertEqual(answer.json()["detail"], "Your ritual already carries those resonances.")
        self.assert_nothing_spent()

    def test_someone_elses_character_cannot_be_attuned(self) -> None:
        stranger = self.make_player("Stranger", room=self.mara.location)
        body = {
            "character_sheet_id": self.mara.sheet_data.pk,
            "primal_resonance_id": self.marrow.pk,
            "outward_resonance_id": self.dawn.pk,
        }

        answer = self.api(self.account_of(stranger)).post(ATTUNE, body, format="json")

        self.assertEqual(answer.status_code, status.HTTP_400_BAD_REQUEST, answer.content)
        self.assert_nothing_spent()
