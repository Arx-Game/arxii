"""Answering a rite live (#4333 slice 5): walkthrough D, design 6; completes #3298.

A tier 1 or 2 rite performed in a scene with a GM prompts that GM, who sends one
of the being's general answers at or below the rolled tier, or one eligible
miracle, or nothing. Text here is labelled placeholders: answer prose is
staff-authored. The fixture is slice 3's: Ysmay, Ombrin's Chosen, in a live scene
at Ombrin's shrine, with a GM running the scene.
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from actions.definitions.worship import (
    AnswerBeingPromptAction,
    ClosePledgeAction,
    PerformWorshipRiteAction,
)
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition
from world.gm.constants import GMLevel, GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.factories import (
    GMLevelCapFactory,
    GMProfileFactory,
    GMPromptFilterFactory,
)
from world.gm.models import GMPrompt
from world.gm.prompt_services import dismiss_gm_prompt, expire_scene_prompts
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneGMParticipationFactory
from world.scenes.models import Interaction
from world.worship.exceptions import StewardAnswerError
from world.worship.factories import (
    AnswerFactory,
    DivineInterventionConfigFactory,
    MiracleFactory,
)
from world.worship.live_services import (
    live_limit_reason,
    live_panel,
    send_live_answer,
)
from world.worship.models import MiraclePerformance, Vision
from world.worship.services import miracle_ineligibility, perform_divine_intervention
from world.worship.tests.test_answers import AnswerTestBase

_ANSWER = "[staff-authored answer text]"
_EDITED = "[GM-edited answer text]"
_ONLOOKER = "[staff-authored onlooker line]"


class LiveTestBase(AnswerTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.gm_profile = GMProfileFactory(level=GMLevel.GM)
        cls.gm_account = cls.gm_profile.account
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm_account)

    def _general(self, tier: str, **kwargs):
        """One of Ombrin's general answers (no pledge type) at ``tier``."""
        return self._full_answer(tier, pledge=None, **kwargs)

    def _perform(self, tier: str):
        with force_check_outcome(self.outcomes[tier]):
            return PerformWorshipRiteAction().run(actor=self.sheet.character, rite=self.rite)

    def _prompts(self):
        return GMPrompt.objects.filter(
            kind=GMPromptKind.BEING_ANSWER, rite_performance__isnull=False
        )

    def _prompt(self) -> GMPrompt:
        return self._prompts().get()

    def _vision_count(self) -> int:
        return Vision.objects.filter(recipient=self.sheet).count()


class RoutingTests(LiveTestBase):
    def test_a_rite_in_a_gm_scene_prompts_the_scene_gm(self) -> None:
        self._general("Partial Success")

        result = self._perform("Partial Success")

        self.assertTrue(result.success, result.message)
        prompt = self._prompt()
        self.assertEqual(prompt.addressed_to, self.gm_account)
        self.assertEqual(prompt.scene, self.scene)
        self.assertEqual(prompt.character_sheet, self.sheet)
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)
        self.assertEqual(prompt.rite_performance.outcome_tier, self.outcomes["Partial Success"])
        # The rite's own award landed as it always does.
        self.assertEqual(self._favor(), 4)

    def test_a_scene_with_no_gm_prompts_nobody(self) -> None:
        self._general("Partial Success")
        self.scene.participations.filter(is_gm=True).delete()
        self.scene.__dict__.pop("participations_cached", None)

        self._perform("Partial Success")

        self.assertFalse(self._prompts().exists())

    def test_a_gm_who_muted_being_answers_is_not_prompted(self) -> None:
        self._general("Partial Success")
        GMPromptFilterFactory(
            account=self.gm_account, group=GMPromptGroup.BEING_ANSWER, enabled=False
        )

        self._perform("Partial Success")

        self.assertFalse(self._prompts().exists())

    def test_a_being_with_nothing_to_offer_prompts_nobody(self) -> None:
        self._perform("Partial Success")
        self.assertFalse(self._prompts().exists())

    def test_closing_rite_no_live_prompt(self) -> None:
        self._general("Success")
        self._ready()
        with force_check_outcome(self.outcomes["Success"]):
            result = ClosePledgeAction().run(actor=self.sheet.character)

        self.assertTrue(result.success, result.message)
        self.assertFalse(self._prompts().exists())
        # The pledge route delivered its own answer instead.
        self.assertEqual(self._vision_count(), 1)

    def test_the_scene_ending_closes_the_prompt_and_sends_nothing(self) -> None:
        self._general("Partial Success")
        self._perform("Partial Success")

        expire_scene_prompts(self.scene)

        self.assertEqual(self._prompt().status, GMPromptStatus.DISMISSED)
        self.assertEqual(self._vision_count(), 0)


class PanelTests(LiveTestBase):
    def test_live_panel_tier_cap(self) -> None:
        partial = self._general("Partial Success")
        failure = self._general("Failure")
        self._general("Success")  # above the roll
        AnswerFactory(  # a pledge type's answer belongs to its pledge, not the live panel
            being=self.being, pledge=self.pledge, outcome_tier=self.outcomes["Failure"]
        )
        AnswerFactory(
            being=self.being, pledge=None, outcome_tier=self.outcomes["Failure"], is_active=False
        )
        self._perform("Partial Success")

        panel = live_panel(self._prompt(), account=self.gm_account)

        self.assertEqual([option.answer for option in panel.answers], [partial, failure])
        self.assertEqual(panel.tier, self.outcomes["Partial Success"])
        self.assertEqual(panel.limit_reason, "")

    def test_the_panel_asks_the_miracle_check_once_not_per_miracle(self) -> None:
        self._general("Partial Success")
        MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        self._perform("Partial Success")
        prompt = self._prompt()
        live_panel(prompt, account=self.gm_account)  # warms the config's cache
        with CaptureQueriesContext(connection) as one:
            live_panel(prompt, account=self.gm_account)

        for _ in range(4):
            MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        with CaptureQueriesContext(connection) as five:
            panel = live_panel(prompt, account=self.gm_account)

        self.assertEqual(len(panel.miracles), 5)
        self.assertEqual(len(five), len(one))

    def test_the_panel_counts_how_often_an_answer_was_used(self) -> None:
        answer = self._general("Partial Success")
        Vision.objects.create(
            recipient=self.sheet, being=self.being, body="[earlier]", answer=answer
        )
        self._perform("Partial Success")

        (option,) = live_panel(self._prompt(), account=self.gm_account).answers

        self.assertEqual(option.used_count, 1)

    def test_a_dismissed_prompt_sends_nothing(self) -> None:
        self._general("Partial Success")
        self._perform("Partial Success")
        prompt = self._prompt()

        dismiss_gm_prompt(prompt, resolver=self.gm_account)

        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertEqual(prompt.resolution_note, "Dismissed: nothing was sent.")
        self.assertEqual(self._vision_count(), 0)
        self.assertEqual(self._favor(), 4)  # the rite's award stands
        # Dismissing used none of the week's limit.
        self.assertEqual(live_limit_reason(self.being, self.sheet), "")


class SendTests(LiveTestBase):
    def test_the_gm_sends_an_answer_as_a_vision(self) -> None:
        answer = self._general("Partial Success", conceals_source=False)
        self._perform("Partial Success")
        prompt = self._prompt()

        sent = send_live_answer(prompt, resolver=self.gm_account, answer=answer)

        self.assertEqual(sent.vision.answer, answer)
        self.assertEqual(sent.vision.sent_by, self.gm_account)
        self.assertEqual(sent.vision.recipient, self.sheet)
        self.assertIn(_ANSWER, sent.vision.body)
        self.assertNotIn("[staff-authored fact text]", sent.vision.body)  # below Success
        self.assertTrue(self._has_condition())  # the answer's cost, as written
        self.assertTrue(self._holds_mission())  # its follow-up clue
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.CONFIRMED)
        self.assertEqual(prompt.resolved_by, self.gm_account)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 90)

    def test_an_answer_above_the_roll_is_refused(self) -> None:
        above = self._general("Success")
        self._general("Failure")  # the roll has something to offer, so the GM is prompted
        self._perform("Partial Success")

        with self.assertRaises(StewardAnswerError) as caught:
            send_live_answer(self._prompt(), resolver=self.gm_account, answer=above)

        self.assertEqual(
            caught.exception.user_message,
            "That answer is not one this being can send at this roll.",
        )
        self.assertEqual(self._vision_count(), 0)

    def test_no_edit_without_a_level_that_may_adapt(self) -> None:
        answer = self._general("Partial Success")
        GMLevelCapFactory(level=GMLevel.GM, may_adapt_answers=False)
        self._perform("Partial Success")

        panel = live_panel(self._prompt(), account=self.gm_account)
        with self.assertRaises(StewardAnswerError) as caught:
            send_live_answer(self._prompt(), resolver=self.gm_account, answer=answer, text=_EDITED)

        self.assertFalse(panel.may_adapt)
        self.assertEqual(
            caught.exception.user_message, "Your GM level does not allow editing an answer."
        )
        self.assertEqual(self._vision_count(), 0)
        self.assertEqual(self._prompt().status, GMPromptStatus.PENDING)

    def test_a_level_that_may_adapt_edits_the_main_text_only(self) -> None:
        answer = self._general("Partial Success")
        GMLevelCapFactory(level=GMLevel.GM, may_adapt_answers=True)
        self._perform("Partial Success")

        panel = live_panel(self._prompt(), account=self.gm_account)
        sent = send_live_answer(
            self._prompt(), resolver=self.gm_account, answer=answer, text=_EDITED
        )

        self.assertTrue(panel.may_adapt)
        self.assertIn(_EDITED, sent.vision.body)
        self.assertNotIn(_ANSWER, sent.vision.body)
        # The cost text, follow-up text, cost and follow-up clue stay as written.
        self.assertIn("[staff-authored cost text]", sent.vision.body)
        self.assertIn("[staff-authored follow-up text]", sent.vision.body)
        self.assertTrue(self._has_condition())
        self.assertTrue(self._holds_mission())
        answer.refresh_from_db()
        self.assertEqual(answer.answer_text, _ANSWER)  # the catalogue row is untouched

    def test_the_onlooker_line_reaches_the_room(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")

        result = AnswerBeingPromptAction().run(
            actor=None,
            account=self.gm_account,
            prompt_id=self._prompt().pk,
            answer_id=answer.pk,
        )

        self.assertTrue(result.success, result.message)
        lines = list(
            Interaction.objects.filter(scene=self.scene, mode=InteractionMode.OUTCOME).values_list(
                "content", flat=True
            )
        )
        self.assertIn(_ONLOOKER, lines)

    def test_only_the_addressed_gm_may_answer(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        other = GMProfileFactory(level=GMLevel.GM).account

        result = AnswerBeingPromptAction().run(
            actor=None, account=other, prompt_id=self._prompt().pk, answer_id=answer.pk
        )

        self.assertFalse(result.success)
        self.assertEqual(self._vision_count(), 0)

    def test_two_gms_cannot_both_answer(self) -> None:
        answer = self._general("Partial Success")
        second = GMProfileFactory(level=GMLevel.GM).account
        SceneGMParticipationFactory(scene=self.scene, account=second)
        self.scene.__dict__.pop("participations_cached", None)
        self._perform("Partial Success")
        mine, theirs = self._prompts().order_by("pk")

        send_live_answer(mine, resolver=mine.addressed_to, answer=answer)

        theirs.refresh_from_db()
        self.assertEqual(theirs.status, GMPromptStatus.DISMISSED)
        with self.assertRaises(StewardAnswerError):
            send_live_answer(theirs, resolver=theirs.addressed_to, answer=answer)
        self.assertEqual(self._vision_count(), 1)

    def test_a_short_pool_refuses_an_answer_and_keeps_the_prompt_open(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        self.being.resonance_pool = 5
        self.being.save(update_fields=["resonance_pool"])

        with self.assertRaises(StewardAnswerError) as caught:
            send_live_answer(self._prompt(), resolver=self.gm_account, answer=answer)

        self.assertIn("worship pool cannot pay", caught.exception.user_message)
        self.assertEqual(self._prompt().status, GMPromptStatus.PENDING)

    def test_one_choice_only(self) -> None:
        answer = self._general("Partial Success")
        miracle = MiracleFactory(being=self.being)
        self._perform("Partial Success")
        for kwargs in ({}, {"answer": answer, "miracle": miracle}):
            with self.assertRaises(StewardAnswerError):
                send_live_answer(self._prompt(), resolver=self.gm_account, **kwargs)


class LimitTests(LiveTestBase):
    def test_live_limit_per_being_and_character(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        send_live_answer(self._prompt(), resolver=self.gm_account, answer=answer)
        self.assertIn("Ombrin has already answered", live_limit_reason(self.being, self.sheet))

        # Another rite this week raises no prompt for the same being and character...
        self._perform("Partial Success")
        self.assertEqual(self._prompts().count(), 1)
        # ...and no prompt that was open before the answer can send a second one.
        stale = GMPrompt.objects.get(pk=self._prompt().pk)
        with self.assertRaises(StewardAnswerError):
            send_live_answer(stale, resolver=self.gm_account, answer=answer)

        # Another character is unaffected by this one's limit.
        self.assertEqual(live_limit_reason(self.being, self.other_sheet), "")

    def test_a_miracle_and_an_answer_count_together(self) -> None:
        answer = self._general("Partial Success")
        miracle = MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        DivineInterventionConfigFactory(favor_threshold=1, min_pool_for_intervention=10)
        self._perform("Partial Success")
        send_live_answer(self._prompt(), resolver=self.gm_account, miracle=miracle)

        self._perform("Partial Success")  # no new prompt
        self.assertEqual(self._prompts().count(), 1)
        self.assertEqual(live_limit_reason(self.being, self.sheet) != "", True)
        # The limit also stops an answer sent from a prompt raised earlier.
        stale = GMPrompt.objects.get(pk=self._prompt().pk)
        stale.status = GMPromptStatus.PENDING  # as a still-open sibling copy would be
        with self.assertRaises(StewardAnswerError):
            send_live_answer(stale, resolver=self.gm_account, answer=answer)

    def test_the_limit_is_per_being(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        send_live_answer(self._prompt(), resolver=self.gm_account, answer=answer)
        other_being = AnswerFactory(outcome_tier=self.outcomes["Failure"]).being
        self.assertEqual(live_limit_reason(other_being, self.sheet), "")

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.character_sheets.factories import CharacterSheetFactory

        cls.other_sheet = CharacterSheetFactory()


class MiracleTests(LiveTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.cooldown = ConditionTemplateFactory(name="Divine Intervention Cooldown")
        DivineInterventionConfigFactory(favor_threshold=1, min_pool_for_intervention=10)

    def test_live_miracle_eligibility(self) -> None:
        """Favor, the pool and the cooldown each grey a miracle with its reason; an
        eligible one runs through ``perform_divine_intervention``."""
        # Ysmay's favor with Ombrin is 0 (DevotionStandingFactory default) until the rite pays.
        low = MiracleFactory(being=self.being, name="Low", favor_threshold=500, sort_order=1)
        MiracleFactory(
            being=self.being, name="Dear", favor_threshold=1, resonance_pool_cost=900, sort_order=2
        )
        fine = MiracleFactory(
            being=self.being, name="Fine", favor_threshold=1, resonance_pool_cost=10, sort_order=3
        )
        retired = MiracleFactory(being=self.being, name="Retired", is_active=False)
        self._general("Partial Success")
        self._perform("Partial Success")
        self.being.refresh_from_db()

        panel = live_panel(self._prompt(), account=self.gm_account)

        names = [option.miracle.name for option in panel.miracles]
        self.assertEqual(names, ["Low", "Dear", "Fine"])
        self.assertNotIn(retired, [option.miracle for option in panel.miracles])
        reasons = {option.miracle.name: option.reason for option in panel.miracles}
        self.assertIn("below this miracle's threshold (500)", reasons["Low"])
        self.assertIn("worship pool", reasons["Dear"])
        self.assertEqual(reasons["Fine"], "")

        with self.assertRaises(StewardAnswerError) as caught:
            send_live_answer(self._prompt(), resolver=self.gm_account, miracle=low)
        self.assertEqual(caught.exception.user_message, reasons["Low"])
        self.assertEqual(self._prompt().status, GMPromptStatus.PENDING)

        sent = send_live_answer(self._prompt(), resolver=self.gm_account, miracle=fine)

        performance = MiraclePerformance.objects.get(miracle=fine)
        self.assertEqual(sent.performance, performance)
        self.assertEqual(performance.target_character, self.sheet)
        self.assertEqual(performance.scene, self.scene)
        self.assertEqual(performance.trigger_event, "live_rite")
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 90)

    def test_the_cooldown_greys_every_miracle(self) -> None:
        miracle = MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        apply_condition(self.sheet.character, self.cooldown, duration_rounds=60)
        self._general("Partial Success")
        self._perform("Partial Success")

        self.assertEqual(
            miracle_ineligibility(self.sheet, miracle),
            "Divine intervention is on cooldown for this character.",
        )
        with self.assertRaises(StewardAnswerError):
            send_live_answer(self._prompt(), resolver=self.gm_account, miracle=miracle)
        self.assertFalse(MiraclePerformance.objects.exists())

    def test_a_miracle_that_fails_before_it_is_done_reopens_the_prompt(self) -> None:
        miracle = MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        self._general("Partial Success")
        self._perform("Partial Success")

        with (
            mock.patch(
                "world.worship.services.perform_divine_intervention", side_effect=RuntimeError
            ),
            self.assertRaises(RuntimeError),
        ):
            send_live_answer(self._prompt(), resolver=self.gm_account, miracle=miracle)

        self.assertEqual(self._prompt().status, GMPromptStatus.PENDING)

    def test_a_failure_after_the_miracle_was_done_does_not_reopen_the_prompt(self) -> None:
        """A second miracle must not be sendable once the first was performed."""
        miracle = MiracleFactory(being=self.being, favor_threshold=1, resonance_pool_cost=10)
        self._general("Partial Success")
        self._perform("Partial Success")
        real = perform_divine_intervention

        def performed_then_failed(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError

        with (
            mock.patch(
                "world.worship.services.perform_divine_intervention",
                side_effect=performed_then_failed,
            ),
            self.assertRaises(RuntimeError),
        ):
            send_live_answer(self._prompt(), resolver=self.gm_account, miracle=miracle)

        self.assertEqual(self._prompt().status, GMPromptStatus.CONFIRMED)
        self.assertEqual(MiraclePerformance.objects.filter(miracle=miracle).count(), 1)

    def test_another_beings_miracle_is_refused(self) -> None:
        foreign = MiracleFactory(favor_threshold=0, resonance_pool_cost=0)
        self._general("Partial Success")
        self._perform("Partial Success")

        with self.assertRaises(StewardAnswerError):
            send_live_answer(self._prompt(), resolver=self.gm_account, miracle=foreign)


class ApiTests(LiveTestBase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.default_format = "json"
        self.client.force_authenticate(self.gm_account)

    def test_the_panel_reads_what_the_gm_may_send(self) -> None:
        answer = self._general("Partial Success", onlooker_line=_ONLOOKER)
        MiracleFactory(being=self.being, name="Low", favor_threshold=500)
        GMLevelCapFactory(level=GMLevel.GM, may_adapt_answers=True)
        self._perform("Partial Success")

        response = self.client.get(f"/api/worship/live-answers/{self._prompt().pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["being_name"], "Ombrin")
        self.assertEqual(body["rite_name"], self.rite.name)
        self.assertEqual(body["outcome_tier_name"], "Partial Success")
        self.assertTrue(body["may_adapt"])
        self.assertEqual(body["limit_reason"], "")
        (option,) = body["answers"]
        self.assertEqual(option["id"], answer.pk)
        self.assertEqual(option["onlooker_line"], _ONLOOKER)
        (miracle,) = body["miracles"]
        self.assertIn("threshold", miracle["reason"])

    def test_another_gm_cannot_read_or_answer_the_panel(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        self.client.force_authenticate(GMProfileFactory(level=GMLevel.GM).account)
        prompt = self._prompt()

        self.assertEqual(
            self.client.get(f"/api/worship/live-answers/{prompt.pk}/").status_code, 404
        )
        response = self.client.post(
            f"/api/worship/live-answers/{prompt.pk}/answer/", {"answer": answer.pk}
        )
        self.assertEqual(response.status_code, 404)

    def test_sending_and_dismissing_through_the_api(self) -> None:
        answer = self._general("Partial Success")
        self._perform("Partial Success")
        prompt = self._prompt()

        refused = self.client.post(f"/api/worship/live-answers/{prompt.pk}/answer/", {})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["detail"], "Choose one answer or one miracle.")

        sent = self.client.post(
            f"/api/worship/live-answers/{prompt.pk}/answer/", {"answer": answer.pk}
        )
        self.assertEqual(sent.status_code, 200, sent.content)
        self.assertEqual(sent.json()["detail"], "Sent as a vision from Ombrin.")
        self.assertEqual(self._vision_count(), 1)

    def test_dismissing_through_the_api_sends_nothing(self) -> None:
        self._general("Partial Success")
        self._perform("Partial Success")
        prompt = self._prompt()

        response = self.client.post(f"/api/worship/live-answers/{prompt.pk}/dismiss/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["detail"], "Dismissed. Nothing was sent.")
        self.assertEqual(self._vision_count(), 0)
        self.assertEqual(GMPrompt.objects.get(pk=prompt.pk).status, GMPromptStatus.DISMISSED)

    def test_the_gm_queue_marks_a_live_prompt(self) -> None:
        self._general("Partial Success")
        self._perform("Partial Success")

        response = self.client.get("/api/gm/prompts/", {"scene": self.scene.pk})

        self.assertEqual(response.status_code, 200, response.content)
        (row,) = [r for r in response.json()["results"] if r["kind"] == GMPromptKind.BEING_ANSWER]
        self.assertTrue(row["being_answer_live"])
        self.assertIsNone(row["being_answer_table"])
        self.assertEqual(
            row["being_answer_summary"],
            f"{row['subject_name']}'s {self.rite.name} to Ombrin (Partial Success).",
        )
