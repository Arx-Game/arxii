"""Answers at the close (#4333 slice 3): walkthrough A steps 3 and 4.

A closing rite that resolves a pledge draws one written-ahead ``Answer`` for its
outcome tier and delivers it as a ``Vision``. Answer text here is labelled
placeholders: answer prose is staff-authored. The fixture is slice 2's (Ysmay,
Ombrin's Chosen at the shrine in a live scene; a favor target of 20).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from actions.definitions.worship import ClosePledgeAction
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.ceremonies.services import sacrifice_items
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.factories import FacetFactory
from world.missions.constants import MissionStatus
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInstance
from world.projects.services import scan_active_projects
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction
from world.worship.answer_services import (
    answer_body,
    deliver_held_answers,
    draw_answer,
    pledge_sacrifices,
)
from world.worship.factories import (
    AnswerFactory,
    AnswerSacrificeLineFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
)
from world.worship.models import PendingAnswer, PledgeDetails, Vision
from world.worship.pledge_services import close_pledge, take_pledge
from world.worship.tests.test_pledges import PledgeTestBase

_DELAY = "[staff-authored delay text]"
_ANSWER = "[staff-authored answer text]"
_FACT = "[staff-authored fact text]"
_COST = "[staff-authored cost text]"
_FOLLOW_UP = "[staff-authored follow-up text]"
_ONLOOKER = "[staff-authored onlooker line]"
_SILK_LINE = "[staff-authored sacrifice line: Silk facet]"


class AnswerTestBase(PledgeTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.codex_entry = CodexEntryFactory(learn_threshold=5)
        cls.fact_clue = ClueFactory(
            target_codex_entry=cls.codex_entry, resolution_mode=ClueResolution.AUTOMATIC
        )
        cls.mission = MissionTemplateFactory()
        MissionNodeFactory(template=cls.mission, key="entry", is_entry=True)
        cls.follow_up_clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=cls.mission,
            resolution_mode=ClueResolution.AUTOMATIC,
        )
        cls.condition = ConditionTemplateFactory(name="Marked by Ombrin")

    def _pool_for(self, outcome_name: str):
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=self.outcomes[outcome_name])
        ConsequenceEffectFactory(consequence=consequence, condition_template=self.condition)
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        return pool

    def _full_answer(self, outcome_name: str, **kwargs):
        """Every part filled; delivery decides which ones the tier carries."""
        fields = {
            "being": self.being,
            "pledge": self.pledge,
            "outcome_tier": self.outcomes[outcome_name],
            "delay_text": _DELAY,
            "answer_text": _ANSWER,
            "fact_text": _FACT,
            "fact_clue": self.fact_clue,
            "cost_text": _COST,
            "cost_pool": self._pool_for(outcome_name),
            "follow_up_text": _FOLLOW_UP,
            "follow_up_clue": self.follow_up_clue,
            "onlooker_line": _ONLOOKER,
        }
        return AnswerFactory(**{**fields, **kwargs})

    def _ready(self) -> PledgeDetails:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)
        return details

    def _close(self, outcome_name: str):
        with force_check_outcome(self.outcomes[outcome_name]):
            return close_pledge(self.sheet, scene=self.scene)

    def _knows_fact(self) -> bool:
        return CharacterCodexKnowledge.objects.filter(
            roster_entry=self.sheet.roster_entry,
            entry=self.codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        ).exists()

    def _holds_mission(self) -> bool:
        return MissionInstance.objects.filter(
            template=self.mission,
            status=MissionStatus.ACTIVE,
            participants__character_id=self.sheet.character.pk,
        ).exists()

    def _has_condition(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.sheet.character, condition=self.condition
        ).exists()


class AnswerModelTests(AnswerTestBase):
    def test_answer_tier_parts_enforced(self) -> None:
        partial = self._full_answer("Partial Success")
        with self.assertRaises(ValidationError) as caught:
            partial.full_clean()
        self.assertEqual(set(caught.exception.message_dict), {"fact_text", "fact_clue"})

        failure = self._full_answer("Failure")
        with self.assertRaises(ValidationError) as caught:
            failure.full_clean()
        self.assertEqual(
            set(caught.exception.message_dict), {"fact_text", "fact_clue", "follow_up_clue"}
        )

        self._full_answer("Success").full_clean()  # every part allowed

    def test_fact_clue_must_state_a_fact(self) -> None:
        answer = self._full_answer("Success", fact_clue=self.follow_up_clue)
        with self.assertRaises(ValidationError) as caught:
            answer.full_clean()
        self.assertIn("fact_clue", caught.exception.message_dict)

    def test_pledge_type_of_another_being_is_refused(self) -> None:
        other = WorshippedBeingFactory(name="Wisket")
        answer = AnswerFactory(
            being=other, pledge=self.pledge, outcome_tier=self.outcomes["Success"]
        )
        with self.assertRaises(ValidationError) as caught:
            answer.full_clean()
        self.assertIn("pledge", caught.exception.message_dict)


class DrawTests(AnswerTestBase):
    def test_draw_answer_order(self) -> None:
        details = self._ready()
        success = self.outcomes["Success"]
        general_lower = AnswerFactory(being=self.being, outcome_tier=self.outcomes["Failure"])
        pledge_lower = AnswerFactory(
            being=self.being, pledge=self.pledge, outcome_tier=self.outcomes["Partial Success"]
        )
        # (3) beats (4) and anything further down.
        self.assertEqual(draw_answer(details, success), pledge_lower)

        general_at = AnswerFactory(being=self.being, outcome_tier=success)
        self.assertEqual(draw_answer(details, success), general_at)  # (2) beats (3)

        pledge_at = AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=success)
        self.assertEqual(draw_answer(details, success), pledge_at)  # (1) first

        # A higher tier is never drawn for a lower close; another pledge type never is.
        AnswerFactory(being=self.being, outcome_tier=self.outcomes["Critical Success"])
        other_pledge = type(self.pledge).objects.create(
            being=self.being, name="Other", closing_rite=self.rite
        )
        AnswerFactory(being=self.being, pledge=other_pledge, outcome_tier=self.outcomes["Failure"])
        self.assertEqual(draw_answer(details, self.outcomes["Failure"]), general_lower)

    def test_draw_skips_inactive_and_already_drawn(self) -> None:
        details = self._ready()
        success = self.outcomes["Success"]
        drawn = AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=success)
        Vision.objects.create(recipient=self.sheet, being=self.being, body="x", answer=drawn)
        AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=success, is_active=False)
        fallback = AnswerFactory(being=self.being, outcome_tier=success)

        self.assertEqual(draw_answer(details, success), fallback)

    def test_no_answer_found_means_no_vision(self) -> None:
        self._ready()
        AnswerFactory(being=self.being, outcome_tier=self.outcomes["Critical Success"])

        outcome = self._close("Success")

        self.assertTrue(outcome.resolved)
        self.assertIsNone(outcome.delivery.answer)
        self.assertFalse(Vision.objects.exists())
        self.assertEqual(outcome.award, 10)  # the closing award still lands


class DeliveryTests(AnswerTestBase):
    def test_close_at_success_delivers_every_part(self) -> None:
        self._ready()
        answer = self._full_answer("Success")

        outcome = self._close("Success")

        vision = Vision.objects.get()
        self.assertEqual(outcome.delivery.vision, vision)
        self.assertEqual(vision.answer, answer)
        self.assertIsNone(vision.sent_by)
        self.assertTrue(vision.reveal_source)
        self.assertEqual(vision.clue, self.fact_clue)
        self.assertEqual(
            vision.body, f"{_DELAY}\n\n{_ANSWER}\n\n{_FACT}\n\n{_COST}\n\n{_FOLLOW_UP}"
        )
        self.assertTrue(self._knows_fact())
        self.assertTrue(self._holds_mission())
        self.assertTrue(self._has_condition())
        self.being.refresh_from_db()
        self.assertEqual(vision.resonance_spent, 10)
        # Telnet reads the narrative message: the same footnotes the web card shows.
        self.assertTrue(
            vision.message.body.endswith(
                f"A clue came with it: {self.fact_clue.name}. A mission came with it: "
                f"{self.follow_up_clue.name}. Condition: Marked by Ombrin."
            )
        )

    def test_close_at_critical_success_draws_success_when_no_critical_is_written(self) -> None:
        self._ready()
        answer = self._full_answer("Success")

        self._close("Critical Success")

        self.assertEqual(Vision.objects.get().answer, answer)
        self.assertTrue(self._knows_fact())

    def test_partial_success_gives_no_fact_but_the_follow_up(self) -> None:
        self._ready()
        # Saved past the form: delivery still leaves out what the tier may not carry.
        self._full_answer("Partial Success")

        self._close("Partial Success")

        vision = Vision.objects.get()
        self.assertNotIn(_FACT, vision.body)
        self.assertIsNone(vision.clue)
        self.assertFalse(self._knows_fact())
        self.assertTrue(self._holds_mission())
        self.assertTrue(self._has_condition())

    def test_failure_gives_no_fact_and_no_follow_up_clue(self) -> None:
        self._ready()
        self._full_answer("Failure")

        self._close("Failure")  # the first failure leaves one retry; nothing is delivered
        self.assertFalse(Vision.objects.exists())
        self._close("Failure")

        vision = Vision.objects.get()
        self.assertNotIn(_FACT, vision.body)
        self.assertIsNone(vision.clue)
        self.assertFalse(CharacterClue.objects.exists())
        self.assertFalse(self._knows_fact())
        self.assertFalse(self._holds_mission())
        self.assertTrue(self._has_condition())  # cost still applies

    def test_conceals_source(self) -> None:
        self._ready()
        self._full_answer("Success", conceals_source=True)

        self._close("Success")

        vision = Vision.objects.get()
        self.assertFalse(vision.reveal_source)
        self.assertNotIn("You know whose vision this is", vision.message.body)
        self.assertIn("source concealed", vision.message.ooc_note)

    def test_the_pledges_prayer_is_answered(self) -> None:
        details = take_pledge(self.sheet, self.pledge, prayer_text="[player-written prayer]")
        self._reach_target(details)
        AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=self.outcomes["Success"])

        self._close("Success")

        self.assertEqual(Vision.objects.get().prayer, details.prayer)

    def test_sacrifice_line_rule_shared_facet(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        wolf = FacetFactory(name="Wolf")
        sacrifice_items(self.sheet, [self._carried_item(20, facet=self.silk)])
        sacrifice_items(self.sheet, [self._carried_item(20, facet=self.silk)])
        sacrifice_items(self.sheet, [self._carried_item(20)])
        answer = AnswerFactory(
            being=self.being,
            pledge=self.pledge,
            outcome_tier=self.outcomes["Success"],
            answer_text=_ANSWER,
        )
        AnswerSacrificeLineFactory(answer=answer, facet=self.silk, text=_SILK_LINE)
        AnswerSacrificeLineFactory(answer=answer, facet=wolf)  # nobody sacrificed Wolf

        body = answer_body(answer, pledge_sacrifices(details))

        names = [offering.item_name for offering in pledge_sacrifices(details)]
        main = body.split("\n\n")[1]
        # One line for Silk; the second Silk item and the plain one are listed by name.
        self.assertEqual(main, f"{_ANSWER} {_SILK_LINE} Also sacrificed: {names[1]}, {names[2]}.")
        self.assertNotIn("Wolf", main)


class HeldAnswerTests(AnswerTestBase):
    def test_held_answer_delivered_when_pool_pays(self) -> None:
        self._ready()
        answer = self._full_answer("Success")
        self.being.resonance_pool = 5
        self.being.save(update_fields=["resonance_pool"])

        outcome = self._close("Success")

        self.assertTrue(outcome.delivery.held)
        self.assertFalse(Vision.objects.exists())
        pending = PendingAnswer.objects.get()
        self.assertEqual(pending.answer, answer)
        self.assertFalse(self._knows_fact())
        self.assertFalse(self._has_condition())

        self.assertEqual(deliver_held_answers(), 0)  # still short: kept, not dropped
        self.assertTrue(PendingAnswer.objects.exists())

        self.being.resonance_pool = 50
        self.being.save(update_fields=["resonance_pool"])
        self.assertEqual(deliver_held_answers(), 1)

        self.assertFalse(PendingAnswer.objects.exists())
        self.assertEqual(Vision.objects.get().answer, answer)
        self.assertTrue(self._knows_fact())
        self.assertTrue(self._holds_mission())
        self.assertTrue(self._has_condition())
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 40)

    def test_a_held_answer_is_not_drawn_again(self) -> None:
        details = self._ready()
        answer = self._full_answer("Success")
        PendingAnswer.objects.create(
            character_sheet=self.sheet, answer=answer, pledge_details=details
        )

        self.assertIsNone(draw_answer(details, self.outcomes["Success"]))


class LapseTests(AnswerTestBase):
    def test_a_lapse_pays_partial_and_delivers_no_answer(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details, 12)
        AnswerFactory(being=self.being, outcome_tier=self.outcomes["Partial Success"])
        AnswerFactory(being=self.being, outcome_tier=self.outcomes["Failure"])
        favor_before = self._favor()
        project = details.project
        project.time_limit = project.started_at
        project.save(update_fields=["time_limit"])

        scan_active_projects()

        self.assertEqual(self._favor(), favor_before + 6)  # Partial Success award 3, at 200%
        self.assertFalse(Vision.objects.exists())
        self.assertFalse(PendingAnswer.objects.exists())


class RoomLineTests(AnswerTestBase):
    def _close_through_the_action(self, outcome_name: str):
        with force_check_outcome(self.outcomes[outcome_name]):
            return ClosePledgeAction().run(actor=self.sheet.character)

    def _room_lines(self) -> list[str]:
        return list(
            Interaction.objects.filter(mode=InteractionMode.OUTCOME)
            .order_by("pk")
            .values_list("content", flat=True)
        )

    def test_onlooker_payloads(self) -> None:
        details = take_pledge(self.sheet, self.pledge, prayer_text="[player-written prayer]")
        self._reach_target(details)
        self._full_answer("Success")

        result = self._close_through_the_action("Success")

        self.assertTrue(result.success, result.message)
        lines = self._room_lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("performs Ombrin's rite."))
        self.assertEqual(lines[1], _ONLOOKER)
        joined = " ".join(lines)
        for private in (_DELAY, _ANSWER, _FACT, _COST, _FOLLOW_UP, "[player-written prayer]"):
            self.assertNotIn(private, joined)

    def test_secret_faith_room_line_omits_player_line(self) -> None:
        WorshipDeclarationFactory(
            character_sheet=self.sheet,
            public_being=WorshippedBeingFactory(),
            secret_being=self.being,
        )
        details = take_pledge(self.sheet, self.pledge, prayer_text="[player-written prayer]")
        self._reach_target(details)
        self._full_answer("Success")

        self._close_through_the_action("Success")

        lines = self._room_lines()
        self.assertEqual(lines[-1], _ONLOOKER)
        self.assertFalse(any("[player-written prayer]" in line for line in lines))

    def test_a_held_answer_sends_no_room_line(self) -> None:
        self._ready()
        self._full_answer("Success")
        self.being.resonance_pool = 0
        self.being.save(update_fields=["resonance_pool"])

        self._close_through_the_action("Success")

        self.assertEqual(len(self._room_lines()), 1)  # the rite line only


class ApiTests(AnswerTestBase):
    def _client(self, account):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_the_recipient_reads_what_came_with_the_vision(self) -> None:
        self._ready()
        self._full_answer("Success")
        self._close("Success")

        row = self._client(self.account).get("/api/worship/visions/").json()["results"][0]

        self.assertEqual(row["clue_name"], self.fact_clue.name)
        self.assertEqual(
            row["follow_up_footnote"], f"A mission came with it: {self.follow_up_clue.name}."
        )
        self.assertEqual(row["condition_names"], ["Marked by Ombrin"])
        self.assertEqual(row["being_name"], "Ombrin")

    def test_staff_see_held_answers_on_the_beings_dashboard(self) -> None:
        from evennia.accounts.models import AccountDB

        self._ready()
        self._full_answer("Success")
        self.being.resonance_pool = 0
        self.being.save(update_fields=["resonance_pool"])
        self._close("Success")
        staff = AccountDB.objects.create_superuser("answerstaff", "s@example.com", "pw-123456")
        base = f"/api/worship/admin/beings/{self.being.pk}"

        held = self._client(staff).get(f"{base}/held-answers/").json()
        overview = self._client(staff).get(f"{base}/overview/").json()

        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["pledge_name"], self.pledge.name)
        self.assertEqual(held[0]["outcome_name"], "Success")
        self.assertEqual(overview["held_answer_count"], 1)
        self.assertEqual(overview["answer_count"], 1)
