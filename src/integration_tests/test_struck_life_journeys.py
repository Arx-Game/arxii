"""Journeys: a struck life shows its text, and its Background is the one text written.

Slice 4 of #4813, the backend half, re-ruled by #5178.

Ysmay begins as a Sleeper: every stage of the life is struck, so the beginnings payload
carries the text her life page shows in place of the stage rows and her beat pool is
empty. She writes her Background at Final Touches, and after finalize it is her
``Profile.background``, word for word. The expected shape comes from the parent spec
(the struck text is a field on the beginning) and the owner's ruling of 2026-11-17: one
Background box replaces Recent History, and a Sleeper writes only that.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_creation.factories import LifeBeatFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin

STRUCK = "As a Sleeper, your new life begins now without any memory of who you might have been."


class AStruckLifeAndItsBackground(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.vault = self.make_room("The Vault")
        self.player = self.make_player("Ysmay", room=self.vault)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Struck", height_min=700, height_max=800)
        self.beginnings.strikes_childhood = True
        self.beginnings.strikes_youth = True
        self.beginnings.strikes_adulthood = True
        self.beginnings.struck_stages_text = STRUCK
        self.beginnings.save()
        LifeBeatFactory(name="Early Upbringing")
        self.draft = self._create_base_draft(first_name="Ysmay")
        self.client = self.api(self.account)

    def test_the_text_shows_the_pool_is_empty_and_the_background_is_what_she_wrote(self):
        res = self.client.get(
            f"/api/character-creation/beginnings/?starting_area={self.beginnings.starting_area.pk}"
        )
        self.assertEqual(res.status_code, 200, res.content)
        rows = res.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        mine = {row["id"]: row for row in rows}[self.beginnings.pk]
        self.assertEqual(mine["struck_stages_text"], STRUCK)

        beats = self.client.get(f"/api/character-creation/drafts/{self.draft.id}/beats/")
        self.assertEqual(beats.json(), [], "every stage is struck, so the pool is empty")

        patched = self.client.patch(
            f"/api/character-creation/drafts/{self.draft.id}/",
            {"draft_data": {"background": "I woke in a tomb that was not mine."}},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)

        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        self.assertEqual(
            character.sheet_data.true_profile.background, "I woke in a tomb that was not mine."
        )
