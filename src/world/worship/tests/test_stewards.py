"""Stewarded beings (#4333 slice 4): walkthrough C.

A ``BeingSteward`` ties a being to one GM table. Only the table's members serve
it; a closing rite of a pledge to it goes to the table's GM as a
``BEING_ANSWER`` prompt; the GM sends an authored answer or (Success and above)
their own text; dismissal or the timeout draws an authored answer. Text here is
labelled placeholders. The fixture is slice 3's: Ysmay, Ombrin's Chosen at the
shrine in a live scene, with Ombrin stewarded by a Senior GM's table she sits at.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from actions.definitions.worship import AnswerBeingPromptAction, ClosePledgeAction
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.ceremonies.models import CeremonyOffering
from world.ceremonies.services import sacrifice_items
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.codex.factories import CodexEntryFactory
from world.gm.constants import GMLevel, GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.factories import (
    GMProfileFactory,
    GMPromptFilterFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.gm.models import GMPrompt
from world.gm.prompt_services import dismiss_gm_prompt, visible_prompts_for
from world.roster.factories import grant_test_tenure
from world.worship.exceptions import (
    PrayerError,
    SacrificeRefused,
    StewardAnswerError,
    StewardedBeingClosed,
)
from world.worship.factories import (
    BeingStewardFactory,
    DevotionStandingFactory,
    TempleDedicationFactory,
    WorshipDeclarationFactory,
)
from world.worship.invocation_services import invocation_refusal
from world.worship.models import BeingSteward, PatronageValence, PendingAnswer, Vision
from world.worship.pledge_services import take_pledge
from world.worship.prayer_services import pray
from world.worship.steward_services import (
    answer_options,
    catalogue_clues,
    expire_steward_prompts,
    god_signs,
    send_steward_answer,
    steward_refusals,
)
from world.worship.tests.test_answers import AnswerTestBase

_GM_TEXT = "[GM-written free text]"


class StewardTestBase(AnswerTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.gm_profile = GMProfileFactory(level=GMLevel.SENIOR)
        cls.gm_account = cls.gm_profile.account
        cls.table = GMTableFactory(gm=cls.gm_profile, name="The Whitlow table")
        GMTableMembershipFactory(table=cls.table, persona=cls.sheet.primary_persona)
        cls.steward = BeingStewardFactory(being=cls.being, table=cls.table)

    def _prompt(self) -> GMPrompt:
        return GMPrompt.objects.get(
            kind=GMPromptKind.BEING_ANSWER, pledge__character_sheet=self.sheet
        )

    def _closed(self, outcome_name: str) -> GMPrompt:
        self._ready()
        self._close(outcome_name)
        return self._prompt()


class StewardAssignmentTests(StewardTestBase):
    def test_a_senior_gm_table_with_no_god_signs_may_steward(self) -> None:
        # Ysmay is Ombrin's Chosen, but she sits at the table, so that is no sign.
        self.assertEqual(steward_refusals(self.being, self.table), [])
        self.steward.full_clean()

    def test_steward_refusal_god_signs(self) -> None:
        other = CharacterSheetFactory()
        DevotionStandingFactory(
            character_sheet=other,
            being=self.being,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        WorshipDeclarationFactory(character_sheet=CharacterSheetFactory(), public_being=self.being)
        TempleDedicationFactory(being=self.being)
        self.being.codex_entry = CodexEntryFactory(is_public=True)
        self.being.save(update_fields=["codex_entry"])

        signs = god_signs(self.being, self.table)

        self.assertEqual(
            signs,
            [
                "It has a public codex entry.",
                "1 character declares it as their public faith.",
                "It has a Chosen who is not seated at this table.",
                "A temple is dedicated to it.",
            ],
        )
        with self.assertRaises(ValidationError) as caught:
            BeingSteward(being=self.being, table=self.table).clean()
        self.assertEqual(len(caught.exception.message_dict["table"]), 4)

    def test_steward_secret_faith_not_a_sign(self) -> None:
        WorshipDeclarationFactory(character_sheet=CharacterSheetFactory(), secret_being=self.being)
        self.assertEqual(god_signs(self.being, self.table), [])

    def test_a_gm_below_senior_is_refused(self) -> None:
        table = GMTableFactory(gm=GMProfileFactory(level=GMLevel.EXPERIENCED))
        refusals = steward_refusals(self.being, table)
        self.assertEqual(
            refusals[0], "The table's GM is Experienced GM; a steward's GM must be Senior GM."
        )


class MembersOnlyTests(StewardTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.stranger = CharacterSheetFactory()
        grant_test_tenure(cls.stranger)
        cls.stranger.character.db_location = cls.room
        cls.stranger.character.save(update_fields=["db_location"])
        DevotionStandingFactory(character_sheet=cls.stranger, being=cls.being, favor=10)

    def test_a_stranger_cannot_pledge_pray_invoke_or_sacrifice(self) -> None:
        expected = "Ombrin answers only to the members of one GM table."
        with self.assertRaises(StewardedBeingClosed) as caught:
            take_pledge(self.stranger, self.pledge)
        self.assertEqual(caught.exception.user_message, expected)
        with self.assertRaises(PrayerError) as caught:
            pray(self.stranger, self.being, "[player-written prayer]")
        self.assertEqual(caught.exception.user_message, expected)
        self.assertEqual(invocation_refusal(self.stranger, self.being), expected)
        item = self._carried_item(20)
        item.game_object.db_location = self.stranger.character
        item.game_object.save(update_fields=["db_location"])
        with self.assertRaises(SacrificeRefused) as caught:
            sacrifice_items(self.stranger, [item], being=self.being)
        self.assertEqual(caught.exception.user_message, expected)

    def test_a_member_sacrifices_to_a_stewarded_being_with_no_shrine(self) -> None:
        elsewhere = ObjectDBFactory(db_key="Road", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=elsewhere)
        self.sheet.character.db_location = elsewhere
        self.sheet.character.save(update_fields=["db_location"])
        item = self._carried_item(20)

        outcome = sacrifice_items(self.sheet, [item], being=self.being)

        self.assertEqual(outcome.being, self.being)
        self.assertEqual(outcome.site, "")
        self.assertTrue(CeremonyOffering.objects.filter(being=self.being).exists())


class StewardRoutingTests(StewardTestBase):
    def test_closing_a_stewarded_pledge_prompts_the_table_gm_and_draws_nothing(self) -> None:
        self._full_answer("Success")
        self._ready()
        with force_check_outcome(self.outcomes["Success"]):
            result = ClosePledgeAction().run(actor=self.sheet.character)

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["awaiting_steward"])
        self.assertIn("Ombrin's answer will come later.", result.message)
        self.assertFalse(Vision.objects.filter(recipient=self.sheet).exists())
        prompt = self._prompt()
        self.assertEqual(prompt.addressed_to, self.gm_account)
        self.assertIsNone(prompt.scene)
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)
        # Scene-less, so it follows the GM: listed outside any scene.
        self.assertIn(prompt, list(visible_prompts_for(self.gm_account, scene=None)))

    def test_a_gm_who_muted_being_answers_is_not_prompted(self) -> None:
        GMPromptFilterFactory(
            account=self.gm_account, group=GMPromptGroup.BEING_ANSWER, enabled=False
        )
        self._full_answer("Success")
        self._ready()
        outcome = self._close("Success")

        self.assertFalse(outcome.delivery.awaiting_steward)
        self.assertIsNotNone(outcome.delivery.vision)
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.BEING_ANSWER).exists())


class StewardAnswerTests(StewardTestBase):
    def test_answer_options_are_at_or_below_the_tier(self) -> None:
        critical = self._full_answer("Critical Success")
        success = self._full_answer("Success")
        partial = self._full_answer("Partial Success", fact_text="", fact_clue=None)
        prompt = self._closed("Success")

        options = answer_options(prompt.pledge)

        self.assertEqual(options, [success, partial])
        self.assertNotIn(critical, options)

    def test_the_steward_sends_an_authored_answer(self) -> None:
        partial = self._full_answer("Partial Success", fact_text="", fact_clue=None)
        prompt = self._closed("Success")

        result = AnswerBeingPromptAction().run(
            actor=None, account=self.gm_account, prompt_id=prompt.pk, answer_id=partial.pk
        )

        self.assertTrue(result.success, result.message)
        vision = Vision.objects.get(recipient=self.sheet)
        self.assertEqual(vision.answer, partial)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.CONFIRMED)
        self.assertEqual(prompt.resolved_by, self.gm_account)
        self.assertTrue(self._holds_mission())

    def test_only_the_addressed_gm_may_answer(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")
        other = GMProfileFactory(level=GMLevel.SENIOR).account

        result = AnswerBeingPromptAction().run(
            actor=None, account=other, prompt_id=prompt.pk, answer_id=answer.pk
        )

        self.assertFalse(result.success)
        self.assertFalse(Vision.objects.filter(recipient=self.sheet).exists())

    def test_free_text_with_a_catalogue_clue_on_success(self) -> None:
        self._full_answer("Success")  # links the fact and follow-up clues
        prompt = self._closed("Success")
        self.assertEqual(
            {clue.pk for clue in catalogue_clues(self.being)},
            {self.fact_clue.pk, self.follow_up_clue.pk},
        )

        delivery = send_steward_answer(
            prompt, resolver=self.gm_account, text=_GM_TEXT, clue=self.follow_up_clue
        )

        vision = delivery.vision
        self.assertEqual(vision.body, _GM_TEXT)
        self.assertEqual(vision.sent_by, self.gm_account)
        self.assertIsNone(vision.answer)
        self.assertTrue(vision.reveal_source)
        self.assertTrue(self._holds_mission())
        self.assertIn("A mission came with it", vision.message.body)

    def test_free_text_is_refused_below_success(self) -> None:
        self._full_answer("Partial Success", fact_text="", fact_clue=None)
        prompt = self._closed("Partial Success")

        with self.assertRaises(StewardAnswerError) as caught:
            send_steward_answer(prompt, resolver=self.gm_account, text=_GM_TEXT)

        self.assertEqual(
            caught.exception.user_message,
            "Your own text can be sent on Success and Critical Success only.",
        )

    def test_a_clue_outside_the_catalogue_is_refused(self) -> None:
        prompt = self._closed("Success")
        stray = ClueFactory(
            target_codex_entry=CodexEntryFactory(), resolution_mode=ClueResolution.AUTOMATIC
        )

        with self.assertRaises(StewardAnswerError):
            send_steward_answer(prompt, resolver=self.gm_account, text=_GM_TEXT, clue=stray)
        self.assertFalse(CharacterClue.objects.filter(clue=stray).exists())

    def test_an_answered_prompt_cannot_be_answered_again(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")
        send_steward_answer(prompt, resolver=self.gm_account, answer=answer)

        with self.assertRaises(StewardAnswerError):
            send_steward_answer(prompt, resolver=self.gm_account, text=_GM_TEXT)
        self.assertEqual(Vision.objects.filter(recipient=self.sheet).count(), 1)


class StewardFallbackTests(StewardTestBase):
    def test_steward_dismiss_draws_an_authored_answer(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        dismiss_gm_prompt(prompt, resolver=self.gm_account)

        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertEqual(prompt.resolution_note, "Dismissed: an authored answer was drawn.")

    def test_steward_timeout_draws_an_authored_answer(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        self.assertEqual(expire_steward_prompts(), 0)  # inside the three-day window
        prompt.created_at = timezone.now() - timedelta(days=3, minutes=1)
        prompt.save(update_fields=["created_at"])

        self.assertEqual(expire_steward_prompts(), 1)

        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)
        prompt.refresh_from_db()
        self.assertEqual(
            prompt.resolution_note, "No answer within 3 days: an authored answer was drawn."
        )

    def test_a_short_pool_holds_the_fallback(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")
        being = prompt.pledge.pledge.being  # the identity-mapped row delivery reads
        # The rollback restores the row, not the cached instance; put it back after.
        self.addCleanup(setattr, being, "resonance_pool", being.resonance_pool)
        being.resonance_pool = 0
        being.save(update_fields=["resonance_pool"])

        with self.assertRaises(StewardAnswerError):
            send_steward_answer(prompt, resolver=self.gm_account, text=_GM_TEXT)
        dismiss_gm_prompt(prompt, resolver=self.gm_account)

        self.assertEqual(PendingAnswer.objects.get(character_sheet=self.sheet).answer, answer)
