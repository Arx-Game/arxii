"""Journeys for a scene GM answering a rite live (#4442, slice 5 of #4333; completes #3298).

Orla performs one of Ombrin's rites in a scene Hobb runs. Hobb is prompted, reads the
answers at or below the roll and the miracles on telnet, and sends one answer, or sends
nothing. Caddoc watches from the room. Answer and onlooker text are labelled placeholders:
answer prose is staff-authored.
"""

from __future__ import annotations

from unittest.mock import patch

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.factories import ActionPointPoolFactory
from world.checks.test_helpers import force_check_outcome
from world.gm.constants import GMLevel
from world.gm.factories import GMLevelCapFactory, GMProfileFactory
from world.gm.models import GMPrompt
from world.scenes.factories import (
    SceneFactory,
    SceneGMParticipationFactory,
    SceneParticipationFactory,
)
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.factories import (
    AnswerFactory,
    BeingResonanceFactory,
    MiracleFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.models import Vision

_ANSWER = "[staff-authored answer text]"
_ONLOOKER = "[staff-authored onlooker line]"


class AGMAnswersARiteLive(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Shrine of Ombrin")
        self.orla = self.make_player("Orla", room=room)
        self.hobb = self.make_player("Hobb", room=room)
        self.caddoc = self.make_player("Caddoc", room=room)
        self.watch(self.orla, self.hobb, self.caddoc)

        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        success = CheckOutcomeFactory(name="Success", success_level=1)
        self.being = WorshippedBeingFactory(name="Ombrin", resonance_pool=100)
        resonance = BeingResonanceFactory(being=self.being, tier=BeingResonanceTier.ASSOCIATED)
        self.rite = WorshipRiteFactory(
            being=self.being,
            kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL),
            name="The Long Watch",
            resonance=resonance,
        )
        for outcome in (self.partial, self.failure, success):
            WorshipRiteTierAwardFactory(
                tier=RiteTier.DEVOTIONAL, outcome_tier=outcome, resonance_amount=2, favor_amount=1
            )
        self.answer = AnswerFactory(
            being=self.being,
            pledge=None,
            outcome_tier=self.partial,
            answer_text=_ANSWER,
            onlooker_line=_ONLOOKER,
        )
        self.miracle = MiracleFactory(being=self.being, name="[miracle name]", favor_threshold=500)
        ActionPointPoolFactory(character=self.orla.sheet_data, current=10, maximum=10)

        self.scene = SceneFactory(location=RoomProfileFactory(objectdb=room), is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.account_of(self.orla))
        SceneParticipationFactory(scene=self.scene, account=self.account_of(self.caddoc))
        gm_account = self.account_of(self.hobb)
        GMProfileFactory(account=gm_account, level=GMLevel.GM)
        GMLevelCapFactory(level=GMLevel.GM, may_adapt_answers=False)
        SceneGMParticipationFactory(scene=self.scene, account=gm_account)

    def _prompt_id(self) -> int:
        return GMPrompt.objects.filter(status="pending").latest("pk").pk

    def _perform_rite(self, outcome) -> None:
        with force_check_outcome(outcome):
            result = self.web(self.orla, "worship_rite", rite=self.rite)
        self.assertTrue(result.detail.success, result.detail.message)

    def test_the_gm_is_prompted_reads_the_panel_and_sends_an_answer(self) -> None:
        self._perform_rite(self.partial)

        prompts = self.telnet(self.hobb, "gm prompts")
        self.assertIn("Being answer", prompts)
        self.assertIn("Orla's The Long Watch to Ombrin (Partial Success).", prompts)

        options = self.telnet(self.hobb, f"gm prompt answer {self._prompt_id()}")
        self.assertIn(f"answer={self.answer.pk} (Partial Success, sent 0 times)", options)
        self.assertIn("[miracle name]: Favor with Ombrin", options)
        # Hobb's level has no edit control.
        self.assertNotIn("text=<words>", options)

        # A harness character has no session, and the room line goes only to non-web
        # sessions; stand one in so the on-commit delivery has somewhere to land.
        on_telnet = patch(
            "world.scenes.interaction_services.non_web_sessions", return_value=[object()]
        )
        with on_telnet, self.captureOnCommitCallbacks(execute=True):
            sent = self.telnet(
                self.hobb, f"gm prompt answer {self._prompt_id()} answer={self.answer.pk}"
            )
        self.assertEqual(sent, "Sent as a vision from Ombrin.")
        # Orla is offline here, so the vision waits for her as a narrative message.
        vision = Vision.objects.get(recipient=self.orla.sheet_data)
        self.assertIn(_ANSWER, vision.body)
        self.assertTold(self.caddoc, _ONLOOKER)
        self.assertNotTold(self.caddoc, _ANSWER)
        self.assertEqual(vision.sent_by.pk, self.account_of(self.hobb).pk)

    def test_the_gm_may_send_nothing(self) -> None:
        self._perform_rite(self.partial)

        self.telnet(self.hobb, f"gm prompt dismiss {self._prompt_id()}")

        self.assertFalse(Vision.objects.filter(recipient=self.orla.sheet_data).exists())
        self.assertEqual(self.telnet(self.hobb, "gm prompts"), "No GM prompts are waiting.")

    def test_a_being_answers_a_character_once_a_week(self) -> None:
        self._perform_rite(self.partial)
        self.telnet(self.hobb, f"gm prompt answer {self._prompt_id()} answer={self.answer.pk}")

        self._perform_rite(self.partial)

        self.assertEqual(self.telnet(self.hobb, "gm prompts"), "No GM prompts are waiting.")
        self.assertEqual(Vision.objects.filter(recipient=self.orla.sheet_data).count(), 1)

    def test_an_edit_is_refused_below_a_level_that_may_adapt_answers(self) -> None:
        self._perform_rite(self.partial)

        refused = self.telnet(
            self.hobb, f"gm prompt answer {self._prompt_id()} answer={self.answer.pk} text=Changed"
        )

        self.assertEqual(refused, "Your GM level does not allow editing an answer.")
        self.assertFalse(Vision.objects.filter(recipient=self.orla.sheet_data).exists())
