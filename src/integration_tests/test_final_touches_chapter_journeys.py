"""Journeys: the Final Touches chapter, card-unlocked lines and Jailbird's crime (#4846).

Slice 5 of #4813, the backend half.

Maud holds no card that asks anything at Final Touches, so the chapter has nothing for
her: no line under ``offers/?chapter=final_touches`` and no prompt. She takes Jailbird
through the distinctions sync, and the chapter opens: the line Jailbird unlocks shows,
named after the card, and the draft asks her to name the crime. She names it, finalize
writes one staff-only crime note, and neither heat nor a deed tag comes of it; her sheet
payload never carries it. The expected shape comes from the parent's rulings of 2026-10-29
(the chapter rule and Jailbird's crime) and decision 6 (no Legend rows, no heat, from
creation).
"""

from __future__ import annotations

import json

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    CRIME_LINE_MAX_LENGTH,
    FinalTouchesPrompt,
    OfferArrival,
    OfferChapter,
)
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.justice.factories import CrimeKindFactory
from world.justice.models import CharacterCrimeNote, DeedCrimeTag, PersonaHeat

CHAPTER_URL = "/api/character-creation/drafts/{pk}/offers/?chapter=final_touches"
SENTENCE = "A purse that was not mine, and a night in the Hollow cells for it."


class TheFinalTouchesChapter(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.room = self.make_room("The Watch House")
        self.player = self.make_player("Maud", room=self.room)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Touches", height_min=700, height_max=800)
        self.jailbird = DistinctionFactory(
            name="Jailbird", cost_per_rank=-5, max_rank=1, final_touches_prompt="crime"
        )
        self.jailbird_offer = DistinctionOfferFactory(
            distinction=self.jailbird,
            chapter=OfferChapter.ACTORS_SHEET,
            arrives_as=OfferArrival.CHOICE,
            prompt="never_do",
        )
        self.escape = DistinctionFactory(name="Escape Artist", cost_per_rank=5, max_rank=1)
        self.escape_offer = DistinctionOfferFactory(
            distinction=self.escape,
            chapter=OfferChapter.FINAL_TOUCHES,
            arrives_as=OfferArrival.CHOICE,
            appearance_section=None,
            unlocked_by=self.jailbird,
        )
        self.theft = CrimeKindFactory(slug="theft", name="Theft")
        self.draft = self._create_base_draft(first_name="Maud")
        self.client = self.api(self.account)

    def _draft_url(self) -> str:
        return f"/api/character-creation/drafts/{self.draft.pk}/"

    def _sync(self, *picks) -> object:
        return self.client.put(
            f"/api/distinctions/drafts/{self.draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": offer.distinction_id, "rank": 1, "offer_id": offer.pk} for offer in picks
                ]
            },
            format="json",
        )

    def test_a_held_card_opens_the_chapter_and_the_named_crime_becomes_a_note(self) -> None:
        # Nothing to tie up: no line, no prompt.
        response = self.client.get(CHAPTER_URL.format(pk=self.draft.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["offers"], [])
        draft_payload = self.client.get(self._draft_url()).json()
        self.assertEqual(draft_payload["final_touches_prompts"], [])
        self.assertIn("Theft", [k["name"] for k in draft_payload["crime_kinds"]])

        # Jailbird taken: the line it unlocks shows, named after the card, and the prompt opens.
        response = self._sync(self.jailbird_offer)
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get(CHAPTER_URL.format(pk=self.draft.pk))
        (line,) = response.json()["offers"]
        self.assertEqual(line["name"], "Escape Artist")
        self.assertEqual(line["opener_label"], "Jailbird")
        self.assertEqual(line["opener_key"], f"unlocked:{self.jailbird.pk}")
        self.assertEqual(
            self.client.get(self._draft_url()).json()["final_touches_prompts"],
            [FinalTouchesPrompt.CRIME.value],
        )

        # The crime: a kind from the list and a sentence; the limits are named.
        too_long = {"kind_id": self.theft.pk, "line": "x" * (CRIME_LINE_MAX_LENGTH + 1)}
        response = self.client.patch(
            self._draft_url(), {"draft_data": {"crime": too_long}}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(str(CRIME_LINE_MAX_LENGTH), response.content.decode())
        response = self.client.patch(
            self._draft_url(), {"draft_data": {"crime": {"kind_id": 999999}}}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        response = self.client.patch(
            self._draft_url(),
            {"draft_data": {"crime": {"kind_id": self.theft.pk, "line": SENTENCE}}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["draft_data"]["crime"]["line"], SENTENCE)

        # Finalize: one note, no heat, no deed tag, nothing on the sheet payload.
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        sheet = character.sheet_data
        (note,) = CharacterCrimeNote.objects.filter(sheet=sheet)
        self.assertEqual(note.crime_kind, self.theft)
        self.assertEqual(note.note, SENTENCE)
        self.assertFalse(PersonaHeat.objects.filter(persona__character_sheet=sheet).exists())
        self.assertFalse(DeedCrimeTag.objects.filter(deed__persona__character_sheet=sheet).exists())
        staff = self.api(AccountFactory(is_staff=True))
        response = staff.get(f"/api/character-sheets/{sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        text = json.dumps(response.json())
        self.assertNotIn(SENTENCE, text)
        self.assertNotIn("Theft", text)

    def test_a_card_without_the_prompt_writes_no_note(self) -> None:
        self.jailbird.final_touches_prompt = ""
        self.jailbird.save(update_fields=["final_touches_prompt"])
        response = self._sync(self.jailbird_offer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(self._draft_url()).json()["final_touches_prompts"], [])
        response = self.client.patch(
            self._draft_url(),
            {"draft_data": {"crime": {"kind_id": self.theft.pk, "line": SENTENCE}}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        self.assertFalse(CharacterCrimeNote.objects.filter(sheet=character.sheet_data).exists())
