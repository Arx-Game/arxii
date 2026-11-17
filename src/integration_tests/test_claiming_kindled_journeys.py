"""Journeys for claiming what a kindled deed set aside (#5181).

Mira stands in The Overseers' Gate with Tomas, who sees only what is posted. Her kindled deeds
have left 5 Ruin (Abyssal) and 3 Mercy (Celestial) waiting to be claimed. Staff wrote the
verbs "gloat" for Abyssal and "inspire" for Celestial, and left the earn rates at 100, so the
numbers are the ones set aside. She collects them by pose (telnet, the scene endpoint, the web
action dispatch) or by a journal entry; the room sees only the pose.

The setup writes the waiting counters directly: how a deed splits into an instant part and a
waiting part is `award_kindled_deeds`' own test (`world/magic/tests/test_kindling.py`).
"""

from __future__ import annotations

import uuid

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.journals.models import JournalEntry
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterResonance,
    Reflection,
    ResonanceGrant,
)
from world.magic.services.resonance import grant_resonance
from world.scenes.models import Interaction

SUBMIT_POSE = "/api/interactions/submit-pose/"
JOURNAL_ENTRIES = "/api/journals/entries/"
PANEL = "/api/magic/kindled-resonances/"
POSE = "laughs as the captain's blade shakes in his hand."
GLOAT = "You gloat. Your Ruin grows by 5."
INSPIRE = "You inspire. Your Mercy grows by 3."


class _Claiming(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        celestial, _primal, abyssal = ensure_conversion_pairs()
        abyssal.claim_verb = "gloat"
        abyssal.save()
        celestial.claim_verb = "inspire"
        celestial.save()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.room = self.make_room("The Overseers' Gate")
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.watch(self.mira, self.tomas)
        self.connect_telnet(self.mira)
        self.connect_telnet(self.tomas)
        self.sheet = self.mira.sheet_data
        set_aura_split(
            CharacterAuraFactory(character=self.sheet), celestial="100", primal="0", abyssal="0"
        )
        self.ruin = ResonanceFactory(name="Ruin", affinity=abyssal)
        self.mercy = ResonanceFactory(name="Mercy", affinity=celestial)
        self.ruin_row = CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.ruin)
        self.mercy_row = CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.mercy)
        for row, waiting in ((self.ruin_row, 5), (self.mercy_row, 3)):
            row.kindled_unclaimed = waiting
            row.save(update_fields=["kindled_unclaimed"])
        self.mira_web = self.api(self.account_of(self.mira))

    def waiting(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).kindled_unclaimed

    def balance(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).balance

    def web_pose(self, content: str = POSE, **fields):
        return self.mira_web.post(
            SUBMIT_POSE,
            {
                "persona_id": self.sheet.primary_persona.pk,
                "content": content,
                "client_request_id": str(uuid.uuid4()),
                **fields,
            },
            format="json",
        )

    def assertRoomSawOnlyThePose(self, text: str = POSE) -> None:  # noqa: N802
        self.assertTold(self.tomas, text)
        for private in ("gloat", "inspire", "grows by", "waiting", "claim"):
            self.assertNotTold(self.tomas, private)


class ClaimingByTelnet(_Claiming):
    def test_pose_claim_collects_everything_waiting_and_tomas_sees_only_the_pose(self) -> None:
        told = self.telnet(self.mira, f"pose/claim {POSE}")

        self.assertIn(GLOAT, told)
        self.assertIn(INSPIRE, told)
        self.assertEqual((self.balance(self.ruin), self.balance(self.mercy)), (5, 3))
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (0, 0))
        self.assertRoomSawOnlyThePose()
        grants = ResonanceGrant.objects.filter(source=GainSource.KINDLED_CLAIM)
        self.assertEqual(sorted(g.amount for g in grants), [3, 5])

    def test_naming_resonances_claims_only_those_whatever_the_case(self) -> None:
        told = self.telnet(self.mira, f"pose/claim RUIN={POSE}")

        self.assertIn(GLOAT, told)
        self.assertNotIn("Mercy", told)
        self.assertEqual((self.balance(self.ruin), self.balance(self.mercy)), (5, 0))
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (0, 3))
        self.assertRoomSawOnlyThePose()

    def test_two_names_claim_both(self) -> None:
        told = self.telnet(self.mira, f"pose/claim ruin,mercy={POSE}")

        self.assertIn(GLOAT, told)
        self.assertIn(INSPIRE, told)

    def test_an_unknown_name_is_refused_and_nothing_posts(self) -> None:
        told = self.telnet(self.mira, f"pose/claim fury={POSE}")

        self.assertIn("nothing waiting to claim in 'fury'", told)
        self.assertNotTold(self.tomas, POSE)
        self.assertFalse(Interaction.objects.filter(content=POSE).exists())
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (5, 3))

    def test_claiming_again_says_nothing_was_waiting_and_still_poses(self) -> None:
        self.telnet(self.mira, f"pose/claim {POSE}")

        told = self.telnet(self.mira, "pose/claim and again.")

        self.assertIn("Nothing was waiting to be claimed.", told)
        self.assertEqual(self.balance(self.ruin), 5)
        self.assertTold(self.tomas, "and again.")

    def test_a_claim_rides_with_a_reflection_on_the_same_pose(self) -> None:
        situation = KindlingSituationFactory(resonance=self.mercy, reason_text="Held the gate")
        grant_resonance(
            self.sheet, self.mercy, 4, source=GainSource.KINDLED_DEED, kindling_situation=situation
        )
        deed = ResonanceGrant.objects.get(source=GainSource.KINDLED_DEED)

        told = self.telnet(self.mira, f"pose/claim/reflect {deed.pk}=embrace {POSE}")

        self.assertIn(GLOAT, told)
        self.assertIn("recorded", told)
        self.assertEqual(Reflection.objects.get().grant, deed)
        self.assertEqual(self.waiting(self.ruin), 0)
        self.assertRoomSawOnlyThePose()


class ClaimingByTheWeb(_Claiming):
    def test_the_scene_endpoint_claims_everything_and_answers_with_the_lines(self) -> None:
        response = self.web_pose(claim=True)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()["claim_lines"], [GLOAT, INSPIRE])
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (0, 0))
        self.assertTold(self.tomas, POSE)
        self.assertNotTold(self.tomas, "gloat")

    def test_a_chosen_subset_leaves_the_rest_waiting(self) -> None:
        response = self.web_pose(claim=True, claim_resonance_ids=[self.mercy.pk])

        self.assertEqual(response.json()["claim_lines"], [INSPIRE])
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (5, 0))

    def test_a_resonance_with_nothing_waiting_is_refused_and_posts_nothing(self) -> None:
        other = ResonanceFactory(name="Wonder")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=other)

        refused = self.web_pose("never posted", claim=True, claim_resonance_ids=[other.pk])

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertFalse(Interaction.objects.filter(content="never posted").exists())
        self.assertEqual(self.waiting(self.ruin), 5)

    def test_a_retry_with_the_same_request_id_claims_once(self) -> None:
        request_id = str(uuid.uuid4())
        fields = {
            "persona_id": self.sheet.primary_persona.pk,
            "content": POSE,
            "client_request_id": request_id,
            "claim": True,
        }
        self.mira_web.post(SUBMIT_POSE, fields, format="json")

        again = self.mira_web.post(SUBMIT_POSE, fields, format="json")

        self.assertEqual(again.status_code, status.HTTP_200_OK, again.content)
        self.assertNotIn("claim_lines", again.json())
        self.assertEqual(self.balance(self.ruin), 5)

    def test_a_claim_rides_with_a_reflection_on_the_scene_endpoint(self) -> None:
        situation = KindlingSituationFactory(resonance=self.mercy, reason_text="Held the gate")
        grant_resonance(
            self.sheet, self.mercy, 4, source=GainSource.KINDLED_DEED, kindling_situation=situation
        )
        deed = ResonanceGrant.objects.get(source=GainSource.KINDLED_DEED)

        response = self.web_pose(claim=True, reflect_choice="EMBRACE", reflect_grant_id=deed.pk)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(len(response.json()["claim_lines"]), 2)
        self.assertIn("reflection_line", response.json())

    def test_the_web_action_dispatch_takes_the_same_claim(self) -> None:
        result = self.web(
            self.mira, "pose", text=POSE, claim=True, claim_resonance_ids=[self.ruin.pk]
        )

        self.assertTrue(result.detail.success, result.detail)
        self.assertEqual(result.detail.message, GLOAT)
        self.assertEqual(result.detail.data, {"claim_lines": [GLOAT]})
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (0, 3))


class ClaimingByJournalEntry(_Claiming):
    def test_a_journal_entry_after_the_scene_claims_what_waited(self) -> None:
        response = self.mira_web.post(
            JOURNAL_ENTRIES,
            {"title": "The captain", "body": "He shook.", "is_public": False, "claim": True},
            format="json",
            HTTP_X_CHARACTER_ID=str(self.mira.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(response.json()["claim_lines"], [GLOAT, INSPIRE])
        self.assertTrue(JournalEntry.objects.filter(title="The captain").exists())
        self.assertEqual((self.waiting(self.ruin), self.waiting(self.mercy)), (0, 0))

    def test_a_named_resonance_with_nothing_waiting_writes_no_entry(self) -> None:
        other = ResonanceFactory(name="Wonder")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=other)

        refused = self.mira_web.post(
            JOURNAL_ENTRIES,
            {
                "title": "Nothing",
                "body": "Nothing.",
                "is_public": False,
                "claim": True,
                "claim_resonance_ids": [other.pk],
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.mira.pk),
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertFalse(JournalEntry.objects.filter(title="Nothing").exists())


class WhatTheResonancesPanelShows(_Claiming):
    def test_the_panel_lists_what_waits_and_each_affinitys_verb_kindled_or_not(self) -> None:
        response = self.mira_web.get(PANEL, {"character_sheet": self.sheet.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        rows = {row["name"]: row for row in response.json()["results"]}
        self.assertEqual(
            (rows["Ruin"]["unclaimed"], rows["Ruin"]["claim_verb"], rows["Ruin"]["kindled"]),
            (5, "gloat", False),
        )
        self.assertEqual((rows["Mercy"]["unclaimed"], rows["Mercy"]["claim_verb"]), (3, "inspire"))

    def test_it_shows_nothing_waiting_after_a_claim(self) -> None:
        self.telnet(self.mira, f"pose/claim {POSE}")

        response = self.mira_web.get(PANEL, {"character_sheet": self.sheet.pk})

        self.assertEqual([row["unclaimed"] for row in response.json()["results"]], [0, 0])

    def test_tomas_cannot_read_miras_waiting_amounts(self) -> None:
        stranger = self.api(self.account_of(self.tomas)).get(
            PANEL, {"character_sheet": self.sheet.pk}
        )

        self.assertEqual(stranger.json()["results"], [])
