"""Pre-PR review fixes for standoffs: real check path, rollback cache, live attack line."""

from types import SimpleNamespace
from unittest.mock import patch

from world.checks.test_helpers import force_check_outcome
from world.standoffs.constants import RevealKind, StandoffGroupState, TermsEffect
from world.standoffs.factories import StandoffApproachFactory, StandoffTermsFactory
from world.standoffs.models import StandoffGroup
from world.standoffs.services.state import begin_round_or_break_standoff
from world.standoffs.services.verbs import (
    standoff_fight,
    standoff_press,
    standoff_read,
    standoff_terms,
)
from world.standoffs.tests.test_verbs import CHECK, VerbBase
from world.traits.factories import CheckOutcomeFactory

BROADCAST = "world.combat.interaction_services.broadcast_action_outcome"


class RealCheckPathTests(VerbBase):
    """The real perform_check and charts run; only the dice outcome is forced."""

    def test_read_on_the_real_check_path(self) -> None:
        self.template.cause = "predation"
        self.template.save(update_fields=["cause"])
        with force_check_outcome(CheckOutcomeFactory(name="Real read", success_level=1)):
            result = standoff_read(self.participant, self.group, focus_kind=RevealKind.CAUSE)
        self.assertTrue(result.success, result.message)
        self.assertEqual([r.kind for r in result.revealed], [RevealKind.CAUSE])

    def test_press_on_the_real_check_path(self) -> None:
        approach = StandoffApproachFactory()
        with force_check_outcome(CheckOutcomeFactory(name="Real press", success_level=1)):
            result = standoff_press(self.participant, self.group, approach)
        self.assertTrue(result.success, result.message)
        self.group.refresh_from_db()
        self.assertEqual(self.group.terms_ease, 1)

    def test_terms_on_the_real_check_path(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        with force_check_outcome(CheckOutcomeFactory(name="Real terms", success_level=1)):
            result = standoff_terms(self.participant, self.group, terms)
        self.assertTrue(result.success, result.message)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.SETTLED)

    def test_terms_with_no_outcome_from_the_chart_is_refused_and_settles_nothing(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        unconfigured = SimpleNamespace(success_level=1, outcome=None, chart=None)
        with patch(CHECK, return_value=unconfigured):
            result = standoff_terms(self.participant, self.group, terms)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You can't do that right now.")
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)


class RollbackCacheTests(VerbBase):
    def test_a_failed_verb_leaves_the_cached_group_matching_the_database(self) -> None:
        approach = StandoffApproachFactory()
        with (
            force_check_outcome(CheckOutcomeFactory(name="Rollback press", success_level=1)),
            patch(
                "world.standoffs.services.verbs.evaluate_causes",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
        ):
            standoff_press(self.participant, self.group, approach)
        self.assertEqual(StandoffGroup.objects.get(pk=self.group.pk).terms_ease, 0)
        self.assertEqual(
            StandoffGroup.objects.values_list("terms_ease", flat=True).get(pk=self.group.pk), 0
        )


class BeginRoundReturnTests(VerbBase):
    def test_breaking_the_standoff_returns_true(self) -> None:
        self.assertTrue(begin_round_or_break_standoff(self.encounter, initiated_by_pc_side=None))

    def test_a_standoff_already_broken_by_another_hand_returns_false(self) -> None:
        with patch("world.standoffs.services.state.is_in_standoff", side_effect=[True, False]):
            began = begin_round_or_break_standoff(self.encounter, initiated_by_pc_side=None)
        self.assertFalse(began)
        self.assertEqual(self.encounter.round_number, 0)


class ActorMessageTests(VerbBase):
    def test_a_botched_terms_that_fires_the_cause_tells_the_actor_they_attack(self) -> None:
        from actions.definitions.standoff import _to_result
        from world.standoffs.types import StandoffActionResult

        result = _to_result(StandoffActionResult(False, "Failure.", fight_started=True))
        self.assertEqual(result.message, "Failure. They attack!")
        fight = _to_result(StandoffActionResult(True, "The fight begins.", fight_started=True))
        self.assertEqual(fight.message, "The fight begins.")


class MoraleShiftLineTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.approach = StandoffApproachFactory(damages_morale=True)

    def _press(self, level: int) -> str:
        outcome = CheckOutcomeFactory(name=f"Morale tier {level}", success_level=level)
        with force_check_outcome(outcome):
            return standoff_press(self.participant, self.group, self.approach).morale_line

    def test_a_press_that_makes_the_group_falter_credits_the_presented_persona(self) -> None:
        from world.scenes.services import active_persona_for_sheet

        for member in self.members:
            member.morale = 55
            member.save(update_fields=["morale"])
        line = self._press(2)  # 30 morale damage: 55 -> 25, down to a break
        who = active_persona_for_sheet(self.participant.character_sheet).name
        self.assertEqual(line, f"{who} shakes the {self.template.name}: they break.")

    def test_a_press_that_leaves_morale_state_alone_sends_no_line(self) -> None:
        self.assertEqual(self._press(1), "")

    def test_a_press_that_only_makes_the_group_falter_says_so(self) -> None:
        for member in self.members:
            member.morale = 70
            member.save(update_fields=["morale"])
        line = self._press(2)  # 70 -> 40: steady to falter
        self.assertTrue(line.endswith(": they falter."), line)


class FightKeywordFlushTests(VerbBase):
    def test_standoff_fight_flush_finds_the_encounter_when_passed_by_keyword(self) -> None:
        boom = RuntimeError("boom")
        with (
            patch("world.standoffs.services.verbs.end_standoff_into_fight", side_effect=boom),
            self.assertRaises(RuntimeError),
        ):
            standoff_fight(participant=self.participant, encounter=self.encounter)
