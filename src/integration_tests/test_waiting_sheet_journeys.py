"""Journeys: a player awaiting approval reads their character's sheet (#5206).

Wren submits a character holding two cards and opens the waiting sheet: her name, both
cards, and the "Submitted" mark. Another player's account is told the sheet does not
exist, and so is a player asking for a draft she never submitted. Staff open the same
sheet. Staff send it back for revisions; Wren lets one card go through the distinctions
sync and the sheet shows the one she kept. After approval, and for a withdrawn draft,
there is no waiting sheet. The expected shapes come from the spec's rulings 3, 5 and 9 and
its leak analysis (404, not 403, for anyone but the draft's account and staff).
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import ApplicationStatus, OfferArrival, OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.models import DraftApplication
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory


def _sheet_url(draft_id: int) -> str:
    return f"/api/character-creation/drafts/{draft_id}/sheet/"


class TheWaitingSheet(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory(username="wren_player")
        self.staff = AccountFactory(username="waiting_staff", is_staff=True)
        self._setup_finalization_base(self, prefix="Waiting", height_min=700, height_max=800)
        self.kept = DistinctionFactory(name="Keen Eyes", cost_per_rank=0)
        self.dropped = DistinctionFactory(name="Old Debts", cost_per_rank=0)
        self.offers = {
            card: DistinctionOfferFactory(
                distinction=card,
                chapter=OfferChapter.ACTORS_SHEET,
                arrives_as=OfferArrival.CHOICE,
                prompt=prompt,
            )
            for card, prompt in ((self.kept, "never_do"), (self.dropped, "fear"))
        }
        self.draft = self._create_base_draft(first_name="Wren")
        self.player = self.api(self.account)
        taken = self._sync(self.kept, self.dropped)
        self.assertEqual(taken.status_code, 200, taken.content)

    def _sync(self, *cards) -> object:
        """The Actor's Sheet's picks through the distinctions sync, as the leaf sends them."""
        return self.player.put(
            f"/api/distinctions/drafts/{self.draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": card.pk, "rank": 1, "offer_id": self.offers[card].pk} for card in cards
                ]
            },
            format="json",
        )

    def _submit(self) -> DraftApplication:
        response = self.player.post(f"/api/character-creation/drafts/{self.draft.pk}/submit/")
        self.assertEqual(response.status_code, 201, response.content)
        return DraftApplication.objects.get(draft=self.draft)

    def _card_names(self, payload: dict) -> list[str]:
        return [row["name"] for row in payload["distinctions"]]

    def test_the_player_and_staff_read_it_while_it_waits(self) -> None:
        # Not yet submitted: there is nothing to read.
        self.assertEqual(self.player.get(_sheet_url(self.draft.pk)).status_code, 404)

        application = self._submit()
        response = self.player.get(_sheet_url(self.draft.pk))
        self.assertEqual(response.status_code, 200, response.content)
        sheet = response.json()
        self.assertTrue(sheet["identity"]["name"].startswith("Wren"))
        self.assertEqual(self._card_names(sheet), ["Keen Eyes", "Old Debts"])
        self.assertEqual(sheet["awaiting"]["status"], ApplicationStatus.SUBMITTED)
        self.assertEqual(sheet["awaiting"]["status_label"], "Submitted")
        self.assertIsNone(sheet["staff_edit"])
        self.assertFalse(sheet["can_edit"])

        stranger = self.api(AccountFactory(username="a_stranger"))
        self.assertEqual(stranger.get(_sheet_url(self.draft.pk)).status_code, 404)
        self.assertIn(self.api().get(_sheet_url(self.draft.pk)).status_code, (401, 403))

        staff = self.api(self.staff)
        response = staff.get(_sheet_url(self.draft.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._card_names(response.json()), ["Keen Eyes", "Old Debts"])

        # In review, then sent back: still readable, and a revision shows at once.
        claim = staff.post(f"/api/character-creation/applications/{application.pk}/claim/")
        self.assertEqual(claim.status_code, 200, claim.content)
        self.assertEqual(
            self.player.get(_sheet_url(self.draft.pk)).json()["awaiting"]["status"],
            ApplicationStatus.IN_REVIEW,
        )
        sent_back = staff.post(
            f"/api/character-creation/applications/{application.pk}/request-revisions/",
            {"comment": "Let one of these go."},
            format="json",
        )
        self.assertEqual(sent_back.status_code, 200, sent_back.content)
        removed = self._sync(self.kept)
        self.assertEqual(removed.status_code, 200, removed.content)
        response = self.player.get(_sheet_url(self.draft.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["awaiting"]["status"], ApplicationStatus.REVISIONS_REQUESTED
        )
        self.assertEqual(self._card_names(response.json()), ["Keen Eyes"])

    def test_a_withdrawn_draft_has_no_waiting_sheet(self) -> None:
        self._submit()
        withdrawn = self.player.post(f"/api/character-creation/drafts/{self.draft.pk}/withdraw/")
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
        self.assertEqual(self.player.get(_sheet_url(self.draft.pk)).status_code, 404)
        self.assertEqual(self.api(self.staff).get(_sheet_url(self.draft.pk)).status_code, 404)

    def test_an_approved_draft_has_no_waiting_sheet(self) -> None:
        application = self._submit()
        staff = self.api(self.staff)
        staff.post(f"/api/character-creation/applications/{application.pk}/claim/")
        approved = staff.post(f"/api/character-creation/applications/{application.pk}/approve/")
        self.assertEqual(approved.status_code, 200, approved.content)
        # The draft is gone with approval; its id answers nothing.
        self.assertEqual(self.player.get(_sheet_url(self.draft.pk)).status_code, 404)
