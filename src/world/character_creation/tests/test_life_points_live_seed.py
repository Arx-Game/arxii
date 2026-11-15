"""The life page's live-server seed (#5141) writes what `frontend/e2e/life-points.spec.ts`
reads, and the draft response carries what the page re-prices its CG points from.

The real-test CI job runs ``seed_life_points_spec`` against a throwaway Postgres database
and a browser reads the result; this runs the seed on the SQLite tier and asks the same
endpoints the page asks, so a broken seed shows up before that job does.

It also holds the one thing the page's arithmetic depends on the server for: a draft
response carries, in ``draft_data.distinctions``, the list its own ``cg_points_spent``
was added up from, each entry with the price it was charged. The page shows the draft's
total, less the prices in that list, plus the prices in the list on screen.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from integration_tests.live_seeds import LIFE_POINTS_BEAT, seed_life_points_spec
from world.character_creation.constants import Stage
from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.character_creation.models import CharacterDraft

ACCOUNT = "e2e_life_points_account"


class LifePointsLiveSeedTests(APITestCase):
    def test_seed_is_idempotent_and_the_page_reads_one_beat_with_two_priced_cards(self) -> None:
        account = AccountFactory(username=ACCOUNT)

        first = seed_life_points_spec(username=ACCOUNT)
        second = seed_life_points_spec(username=ACCOUNT)
        self.assertEqual(first, second)
        draft = CharacterDraft.objects.get(pk=first.draft_id)
        self.assertEqual(draft.current_stage, Stage.LINEAGE)

        self.client.force_authenticate(user=account)
        base = f"/api/character-creation/drafts/{first.draft_id}"
        beats = self.client.get(f"{base}/beats/").json()
        self.assertEqual([beat["name"] for beat in beats], [LIFE_POINTS_BEAT], beats)
        offers = self.client.get(f"{base}/offers/", {"chapter": "backgrounds"}).json()["offers"]
        self.assertEqual(
            {offer["name"]: offer["cost_per_rank"] for offer in offers},
            {first.costly_card: first.costly_price, first.paying_card: -first.paying_price},
        )
        self.assertEqual(
            sorted(beats[0]["answer_offer_ids"]), sorted(offer["offer_id"] for offer in offers)
        )
        # Another account's draft, on another beginning, never meets the beat.
        other = AccountFactory(username="someone_else")
        elsewhere = CharacterDraftFactory(account=other, selected_beginnings=BeginningsFactory())
        self.client.force_authenticate(user=other)
        self.assertEqual(
            self.client.get(f"/api/character-creation/drafts/{elsewhere.pk}/beats/").json(), []
        )

    def test_the_draft_carries_the_priced_list_its_total_was_added_from(self) -> None:
        account = AccountFactory(username=ACCOUNT)
        seed = seed_life_points_spec(username=ACCOUNT)
        self.client.force_authenticate(user=account)
        base = f"/api/character-creation/drafts/{seed.draft_id}"
        offers = {
            offer["name"]: offer
            for offer in self.client.get(f"{base}/offers/", {"chapter": "backgrounds"}).json()[
                "offers"
            ]
        }
        before = self.client.get(f"{base}/").json()
        self.assertEqual(before["draft_data"]["distinctions"], [])
        budget = before["cg_points_spent"] + before["cg_points_remaining"]

        def save(*names: str) -> list[dict]:
            body = {
                "distinctions": [
                    {
                        "id": offers[name]["distinction_id"],
                        "rank": 1,
                        "offer_id": offers[name]["offer_id"],
                    }
                    for name in names
                ]
            }
            resp = self.client.put(
                f"/api/distinctions/drafts/{seed.draft_id}/distinctions/sync/", body, format="json"
            )
            self.assertEqual(resp.status_code, 200, resp.content)
            return resp.json()["distinctions"]

        for names, moved in (
            ((seed.costly_card,), seed.costly_price),
            ((seed.costly_card, seed.paying_card), seed.costly_price - seed.paying_price),
            ((), 0),
        ):
            saved = save(*names)
            # The save's answer prices each pick at its offer's price per rank.
            self.assertEqual(
                {entry["distinction_name"]: entry["cost"] for entry in saved},
                {name: offers[name]["cost_per_rank"] for name in names},
            )
            after = self.client.get(f"{base}/").json()
            # The draft carries the same list, and its total moved by that list's prices.
            self.assertEqual(after["draft_data"]["distinctions"], saved)
            self.assertEqual(after["cg_points_spent"], before["cg_points_spent"] + moved)
            self.assertEqual(after["cg_points_remaining"], budget - after["cg_points_spent"])
            points = self.client.get(f"{base}/cg-points/").json()
            self.assertEqual(points["remaining"], after["cg_points_remaining"])
