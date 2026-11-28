"""Journeys for reflections (#5124): a pose or a journal entry that says what it reflects on.

Mira stands in The Overseers' Gate with Tomas. She is unsettled: she is Celestial through
and through, and her Domination (Abyssal, 30 against 170 Celestial) has grown past who she is.
She has one kindled deed on her ledger, "Barred the overseers' door", which earned her
5 Wonder. A pose or a journal entry can carry a "Reflecting on" row naming that deed or her
Domination and Embrace or Disown. Posting records the reflection and changes nothing yet; the
room sees only the pose. A gain her player marked on an act is a deed too (#5327), unless staff
or the scene's GM undid it.
"""

from __future__ import annotations

from unittest.mock import patch
import uuid

from rest_framework import status

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.journals.models import JournalEntry
from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import ReflectionError
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import Affinity, AffinityInteraction, Reflection, ResonanceGrant
from world.magic.services.reflection import reflectable_for
from world.magic.services.resonance import grant_resonance
from world.narrative.models import NarrativeMessageDelivery
from world.scenes.models import Interaction

SUBMIT_POSE = "/api/interactions/submit-pose/"
JOURNAL_ENTRIES = "/api/journals/entries/"
REFLECTABLES = "/api/magic/reflectables/"
POSE = "kneels at the altar and says nothing."
LATE = ReflectionError("That deed was taken a moment ago.")


class _Reflecting(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        celestial, _primal, abyssal = ensure_conversion_pairs()
        self.room = self.make_room("The Overseers' Gate")
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.watch(self.mira, self.tomas)
        self.connect_telnet(self.mira)
        self.connect_telnet(self.tomas)
        self.sheet = self.mira.sheet_data
        self.wonder = ResonanceFactory(name="Wonder", affinity=celestial)
        self.domination = ResonanceFactory(name="Domination", affinity=abyssal)
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="100", primal="0", abyssal="0")
        for resonance, lifetime in ((self.wonder, 170), (self.domination, 30)):
            row = CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance)
            row.lifetime_earned = lifetime
            row.save()
        situation = KindlingSituationFactory(
            resonance=self.wonder, reason_text="Barred the overseers' door"
        )
        grant_resonance(
            self.sheet,
            self.wonder,
            5,
            source=GainSource.KINDLED_DEED,
            kindling_situation=situation,
        )
        self.deed = ResonanceGrant.objects.get(source=GainSource.KINDLED_DEED)
        self.mira_web = self.api(self.account_of(self.mira))


class WhatMiraCanReflectOn(_Reflecting):
    def test_telnet_reflect_lists_her_domination_and_the_deed_by_number(self) -> None:
        told = self.telnet(self.mira, "reflect")

        self.assertIn("Domination", told)
        self.assertIn("unsettling you", told)
        self.assertIn(f"#{self.deed.pk}", told)
        self.assertIn("Barred the overseers' door", told)

    def test_the_api_lists_the_same_choices_for_her_own_sheet_only(self) -> None:
        response = self.mira_web.get(REFLECTABLES, {"character_sheet": self.sheet.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(
            [(r["kind"], r["id"], r["replaces_waiting"]) for r in response.json()["results"]],
            [("deed", self.deed.pk, False), ("resonance", self.domination.pk, False)],
        )
        stranger = self.api(self.account_of(self.tomas)).get(
            REFLECTABLES, {"character_sheet": self.sheet.pk}
        )
        self.assertEqual(stranger.json()["results"], [])


class ReflectingInAPose(_Reflecting):
    def test_the_room_sees_only_the_pose_and_mira_is_told_it_is_recorded(self) -> None:
        told = self.telnet(self.mira, f"pose/reflect {self.deed.pk}=embrace {POSE}")

        self.assertIn("Your reflection on Barred the overseers' door is recorded", told)
        self.assertTold(self.tomas, POSE)
        for word in ("reflect", "embrace", "recorded", "Barred the overseers"):
            self.assertNotTold(self.tomas, word)
        reflection = Reflection.objects.get()
        self.assertEqual(
            (reflection.grant, reflection.choice, reflection.rite),
            (self.deed, ReflectionChoice.EMBRACE, None),
        )
        self.assertEqual(reflection.interaction.content, POSE)

    def test_a_deed_can_be_reflected_on_only_once_and_the_second_pose_is_not_posted(self) -> None:
        self.telnet(self.mira, f"pose/reflect {self.deed.pk}=embrace {POSE}")

        told = self.telnet(self.mira, f"pose/reflect {self.deed.pk}=disown a second pose")

        self.assertIn("already reflected on that deed", told)
        self.assertNotTold(self.tomas, "a second pose")
        self.assertEqual(Reflection.objects.count(), 1)

    def test_a_newer_reflection_on_her_domination_replaces_the_one_still_waiting(self) -> None:
        self.telnet(self.mira, "pose/reflect Domination=embrace I give in.")

        self.telnet(self.mira, "pose/reflect domination=disown I take it back.")

        reflection = Reflection.objects.get()
        self.assertEqual(
            (reflection.resonance, reflection.choice),
            (self.domination, ReflectionChoice.DISOWN),
        )

    def test_a_resonance_that_is_not_unsettling_her_is_refused_before_the_pose_posts(self) -> None:
        told = self.telnet(self.mira, "pose/reflect Wonder=embrace Wonder fills me.")

        self.assertIn("not a deed or what is unsettling you", told)
        self.assertNotTold(self.tomas, "Wonder fills me")
        self.assertFalse(Reflection.objects.exists())

    def test_a_settled_character_cannot_reflect_on_a_resonance_at_all(self) -> None:
        told = self.telnet(self.tomas, "pose/reflect Domination=embrace Hm.")

        self.assertIn("not what is unsettling you", told)
        self.assertNotTold(self.mira, "Hm.")

    def test_a_plain_pose_and_the_unknown_switch_behave_as_before(self) -> None:
        self.telnet(self.mira, f"pose {POSE}")
        self.assertTold(self.tomas, POSE)
        self.assertFalse(Reflection.objects.exists())

        told = self.telnet(self.mira, "pose/nonsense hello")
        self.assertIn("Usage: pose", told)

    def test_the_web_scene_pose_records_it_and_a_retry_does_not_record_it_twice(self) -> None:
        body = {
            "persona_id": self.sheet.primary_persona.pk,
            "content": POSE,
            "client_request_id": str(uuid.uuid4()),
            "reflect_choice": "DISOWN",
            "reflect_resonance_id": self.domination.pk,
        }
        with self.captureOnCommitCallbacks(execute=True):
            first = self.mira_web.post(SUBMIT_POSE, body, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        self.assertIn(
            "Your reflection on your Domination is recorded", first.json()["reflection_line"]
        )
        reflection = Reflection.objects.get()
        self.assertEqual(reflection.interaction_id, first.json()["id"])
        self.assertEqual(Interaction.objects.filter(content=POSE).count(), 1)

        retry = self.mira_web.post(SUBMIT_POSE, body, format="json")
        self.assertEqual(retry.status_code, status.HTTP_200_OK, retry.content)
        self.assertEqual(Reflection.objects.count(), 1)

    def test_the_web_pose_refuses_a_deed_already_reflected_on_and_posts_nothing(self) -> None:
        self.telnet(self.mira, f"pose/reflect {self.deed.pk}=embrace {POSE}")

        refused = self.mira_web.post(
            SUBMIT_POSE,
            {
                "persona_id": self.sheet.primary_persona.pk,
                "content": "never posted",
                "client_request_id": str(uuid.uuid4()),
                "reflect_choice": "EMBRACE",
                "reflect_grant_id": self.deed.pk,
            },
            format="json",
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn("already reflected", refused.json()["detail"])
        self.assertFalse(Interaction.objects.filter(content="never posted").exists())

    def test_the_web_action_dispatch_takes_the_same_reflection(self) -> None:
        result = self.web(
            self.mira,
            "pose",
            text=POSE,
            reflect_choice="EMBRACE",
            reflect_grant_id=self.deed.pk,
        )

        self.assertTrue(result.detail.success, result.detail)
        self.assertEqual(Reflection.objects.get().grant, self.deed)
        # The recorded line is a success the client shows as one; the pose carried no mark, so
        # the mark's own line is empty.
        self.assertEqual(result.detail.data, {"reflection_recorded": True, "mark_line": ""})

    def test_a_reflection_that_fails_after_the_pose_posts_is_flagged_as_an_error(self) -> None:
        with (
            patch("world.magic.services.reflection.record_reflection", side_effect=LATE),
            patch("world.magic.services.reflection.record_pending_reflection", side_effect=LATE),
        ):
            result = self.web(
                self.mira,
                "pose",
                text=POSE,
                reflect_choice="EMBRACE",
                reflect_grant_id=self.deed.pk,
            )

        # The pose stands; the line says the reflection was not recorded, and the result
        # carries the flag that lets the client show it as the error it is.
        self.assertTrue(result.detail.success, result.detail)
        self.assertIn("not recorded", result.detail.message)
        self.assertEqual(result.detail.data, {"reflection_recorded": False, "mark_line": ""})
        self.assertFalse(Reflection.objects.exists())


class ReflectingInAJournalEntry(_Reflecting):
    def test_telnet_journal_reflect_writes_the_entry_and_records_the_reflection(self) -> None:
        told = self.telnet(
            self.mira,
            "journal/reflect Domination=disown title=The collar body=I am putting it down.",
        )

        self.assertIn("You write a new journal entry: The collar.", told)
        self.assertIn("Your reflection on your Domination is recorded", told)
        entry = JournalEntry.objects.get(title="The collar")
        reflection = Reflection.objects.get()
        self.assertEqual(
            (reflection.journal_entry, reflection.resonance, reflection.choice),
            (entry, self.domination, ReflectionChoice.DISOWN),
        )

    def test_the_web_editor_records_a_private_entry_reflecting_on_a_deed(self) -> None:
        response = self.mira_web.post(
            JOURNAL_ENTRIES,
            {
                "title": "The door",
                "body": "I barred it.",
                "is_public": False,
                "reflect_choice": "EMBRACE",
                "reflect_grant_id": self.deed.pk,
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.mira.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        reflection = Reflection.objects.get()
        self.assertEqual(reflection.journal_entry_id, response.json()["id"])
        self.assertEqual(reflection.grant, self.deed)

    def test_a_refused_reflection_writes_no_entry(self) -> None:
        response = self.mira_web.post(
            JOURNAL_ENTRIES,
            {
                "title": "Nothing",
                "body": "Wonder.",
                "is_public": True,
                "reflect_choice": "EMBRACE",
                "reflect_resonance_id": self.wonder.pk,
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.mira.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("not what is unsettling you", response.json()["detail"])
        self.assertFalse(JournalEntry.objects.filter(title="Nothing").exists())


class ARetryOfAReflectingPose(_Reflecting):
    def _body(self, **extra) -> dict:
        return {
            "persona_id": self.sheet.primary_persona.pk,
            "content": POSE,
            "client_request_id": str(uuid.uuid4()),
            "reflect_choice": "EMBRACE",
            "reflect_grant_id": self.deed.pk,
            **extra,
        }

    def test_a_web_retry_with_the_same_request_id_is_the_replay_not_a_refusal(self) -> None:
        body = self._body()
        with self.captureOnCommitCallbacks(execute=True):
            first = self.mira_web.post(SUBMIT_POSE, body, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)

        retry = self.mira_web.post(SUBMIT_POSE, body, format="json")

        self.assertEqual(retry.status_code, status.HTTP_200_OK, retry.content)
        self.assertEqual(retry.json()["id"], first.json()["id"])
        self.assertEqual(Reflection.objects.get().grant, self.deed)
        self.assertEqual(Interaction.objects.filter(content=POSE).count(), 1)

    def test_a_retry_through_the_pose_action_is_answered_as_a_replay(self) -> None:
        request_id = str(uuid.uuid4())
        kwargs = {
            "text": POSE,
            "client_request_id": request_id,
            "reflect_choice": "EMBRACE",
            "reflect_grant_id": self.deed.pk,
        }
        first = self.web(self.mira, "pose", **kwargs)
        self.assertTrue(first.detail.success, first.detail.message)

        retry = self.web(self.mira, "pose", **kwargs)

        self.assertTrue(retry.detail.success, retry.detail.message)
        self.assertEqual(Reflection.objects.count(), 1)
        self.assertEqual(Interaction.objects.filter(content=POSE).count(), 1)


class AReflectionThatFailsAfterThePoseIsDown(_Reflecting):
    def test_the_web_pose_stands_and_the_writer_is_told_why_it_was_not_recorded(self) -> None:
        with patch("world.scenes.interaction_views.record_pending_reflection", side_effect=LATE):
            response = self.mira_web.post(
                SUBMIT_POSE,
                {
                    "persona_id": self.sheet.primary_persona.pk,
                    "content": POSE,
                    "client_request_id": str(uuid.uuid4()),
                    "reflect_choice": "EMBRACE",
                    "reflect_grant_id": self.deed.pk,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertFalse(response.json()["reflection_recorded"])
        self.assertIn(
            "posted, but your reflection was not recorded", response.json()["reflection_line"]
        )
        self.assertIn("That deed was taken a moment ago.", response.json()["reflection_line"])
        self.assertEqual(Interaction.objects.filter(content=POSE).count(), 1)
        self.assertFalse(Reflection.objects.exists())

    def test_the_pose_action_stands_and_tells_the_poser_why(self) -> None:
        with patch("world.magic.services.reflection.record_pending_reflection", side_effect=LATE):
            told = self.telnet(self.mira, f"pose/reflect {self.deed.pk}=embrace {POSE}")

        self.assertIn("posted, but your reflection was not recorded", told)
        self.assertIn("That deed was taken a moment ago.", told)
        self.assertTold(self.tomas, POSE)
        self.assertFalse(Reflection.objects.exists())

    def test_the_journal_is_rolled_back_whole_and_refused_plainly(self) -> None:
        with patch("world.magic.services.reflection.record_pending_reflection", side_effect=LATE):
            response = self.mira_web.post(
                JOURNAL_ENTRIES,
                {
                    "title": "Rolled back",
                    "body": "Never kept.",
                    "is_public": False,
                    "reflect_choice": "EMBRACE",
                    "reflect_grant_id": self.deed.pk,
                },
                format="json",
                HTTP_X_CHARACTER_ID=str(self.mira.pk),
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertEqual(response.json()["detail"], "That deed was taken a moment ago.")
        self.assertFalse(JournalEntry.objects.filter(title="Rolled back").exists())


class AMarkedDeed(_Reflecting):
    """Mira marked an act with Wonder (6 of it); the gain is a deed she can reflect on."""

    def setUp(self) -> None:
        super().setUp()
        ledger: list[ResonanceGrant] = []
        grant_resonance(
            self.sheet,
            self.wonder,
            6,
            source=GainSource.MARKED_ACT,
            deed_label="Intimidated Hale",
            ledger_out=ledger,
        )
        self.marked = ledger[-1]

    def test_it_is_listed_by_number_with_what_she_did(self) -> None:
        told = self.telnet(self.mira, "reflect")

        self.assertIn(f"#{self.marked.pk}", told)
        self.assertIn("Intimidated Hale", told)
        self.assertIn(f"#{self.deed.pk}", told)

    def test_once_staff_undo_it_it_is_no_deed_and_she_is_told_who_undid_what(self) -> None:
        staff = self.api(AccountFactory(is_staff=True))

        with self.captureOnCommitCallbacks(execute=True):
            undone = staff.post(f"/api/magic/resonance-grants/{self.marked.pk}/undo/")

        self.assertEqual(undone.status_code, status.HTTP_200_OK, undone.content)
        self.assertIn(
            "Staff undid your Wonder reward for Intimidated Hale. Your Wonder falls by 6.",
            "\n".join(
                NarrativeMessageDelivery.objects.filter(
                    recipient_character_sheet=self.sheet
                ).values_list("message__body", flat=True)
            ),
        )
        listed = self.telnet(self.mira, "reflect")
        self.assertNotIn("Intimidated Hale", listed)
        self.assertIn(f"#{self.deed.pk}", listed)
        refused = self.telnet(self.mira, f"pose/reflect {self.marked.pk}=embrace Too late.")
        self.assertIn("not a deed you can reflect on", refused)
        self.assertNotTold(self.tomas, "Too late.")
        self.assertFalse(Reflection.objects.exists())


class AnotherCharactersDeed(_Reflecting):
    def test_telnet_refuses_it_and_posts_nothing(self) -> None:
        told = self.telnet(self.tomas, f"pose/reflect {self.deed.pk}=embrace Mine now.")

        self.assertIn("not a deed you can reflect on", told)
        self.assertNotTold(self.mira, "Mine now.")
        self.assertFalse(Reflection.objects.exists())

    def test_the_web_pose_refuses_it(self) -> None:
        refused = self.api(self.account_of(self.tomas)).post(
            SUBMIT_POSE,
            {
                "persona_id": self.tomas.sheet_data.primary_persona.pk,
                "content": "Mine now.",
                "client_request_id": str(uuid.uuid4()),
                "reflect_choice": "EMBRACE",
                "reflect_grant_id": self.deed.pk,
            },
            format="json",
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertFalse(Interaction.objects.filter(content="Mine now.").exists())

    def test_a_sheetless_actor_has_nothing_to_reflect_on(self) -> None:
        reflectable = reflectable_for(None)

        self.assertEqual((reflectable.deeds, reflectable.unsettling), ((), None))
        self.assertEqual(reflectable.options, ())
