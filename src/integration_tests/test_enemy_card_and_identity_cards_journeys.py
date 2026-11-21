"""Journeys: the enemy a card starts you with, and the cards picked on Identity (#5255).

Owner rulings of 2026-11-21. The enemy section of Final Touches is asked only of a draft
holding a card that starts the character with an enemy: "invisible unless someone has
selected a distinction where they start with an enemy". The personality cards are picked
on the Identity stage.

Maud holds no such card. An enemy saved on her draft pays her nothing, the draft asks no
enemy prompt, and finalize writes no enemy. She takes Old Grudge through the distinctions
sync: the draft now asks for the enemy, the same saved enemy pays its price, and finalize
writes it to her sheet. The price is the authored table's (a house's reach, thwarted: 16),
never read back from the code under test.

Separately, the Identity chapter lists Indolent for her with no opener to satisfy; she
takes it, the draft's spent points rise by the card's cost, and the finished sheet holds it.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_creation.constants import FinalTouchesPrompt, OfferArrival, OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.models import CharacterEnemy
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.societies.constants import EnemyReach
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory

IDENTITY_URL = "/api/character-creation/drafts/{pk}/offers/?chapter=identity"
# A house's reach at "thwarted", from the rate card the owner approved on #3621.
HOUSE_THWARTED_PRICE = 16


class TheEnemyACardStartsYouWith(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.room = self.make_room("The Lamplit Stair")
        self.player = self.make_player("Maud", room=self.room)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Grudge", height_min=700, height_max=800)
        self.grudge = DistinctionFactory(
            name="Old Grudge",
            cost_per_rank=0,
            max_rank=1,
            final_touches_prompt=FinalTouchesPrompt.ENEMY,
        )
        self.grudge_offer = DistinctionOfferFactory(
            distinction=self.grudge, chapter=OfferChapter.IDENTITY, arrives_as=OfferArrival.CHOICE
        )
        house = OrganizationTypeFactory(name="noble house", reach=EnemyReach.HOUSE)
        self.rivals = OrganizationFactory(name="House Thornwood", org_type=house)
        self.draft = self._create_base_draft(first_name="Maud")
        self.client = self.api(self.account)

    def _draft_url(self) -> str:
        return f"/api/character-creation/drafts/{self.draft.pk}/"

    def _payload(self) -> dict:
        response = self.client.get(self._draft_url())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

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

    def _save_the_enemy(self) -> None:
        enemy = {
            "kind": "group",
            "organization_id": self.rivals.pk,
            "name": "",
            "power_tier": "",
            "degree": "thwarted",
            "why": "A debt my mother never paid.",
            "public_line": "The Thornwoods and I do not dine together.",
        }
        response = self.client.patch(
            self._draft_url(), {"draft_data": {"enemy": enemy}}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_an_enemy_counts_only_while_a_card_asks_for_one(self) -> None:
        before = self._payload()
        self.assertNotIn(FinalTouchesPrompt.ENEMY.value, before["final_touches_prompts"])

        # No card asks: the saved enemy is kept and pays nothing.
        self._save_the_enemy()
        unasked = self._payload()
        self.assertEqual(unasked["draft_data"]["enemy"]["degree"], "thwarted")
        self.assertNotIn(FinalTouchesPrompt.ENEMY.value, unasked["final_touches_prompts"])
        self.assertEqual(unasked["cg_points_spent"], before["cg_points_spent"])

        # Old Grudge taken: the draft asks for the enemy and the same answer is paid.
        response = self._sync(self.grudge_offer)
        self.assertEqual(response.status_code, 200, response.content)
        asked = self._payload()
        self.assertEqual(asked["final_touches_prompts"], [FinalTouchesPrompt.ENEMY.value])
        (card,) = [c for c in asked["final_touches_cards"] if c["prompt"] == "enemy"]
        self.assertEqual(card["name"], "Old Grudge")
        self.assertEqual(asked["cg_points_spent"], before["cg_points_spent"] - HOUSE_THWARTED_PRICE)

        # Let go again: the price leaves with the card, the answer stays for its return.
        response = self._sync()
        self.assertEqual(response.status_code, 200, response.content)
        let_go = self._payload()
        self.assertEqual(let_go["final_touches_prompts"], [])
        self.assertEqual(let_go["cg_points_spent"], before["cg_points_spent"])
        self.assertEqual(let_go["draft_data"]["enemy"]["organization_id"], self.rivals.pk)

    def test_finalize_writes_the_enemy_only_for_a_draft_holding_the_card(self) -> None:
        self._save_the_enemy()
        response = self._sync(self.grudge_offer)
        self.assertEqual(response.status_code, 200, response.content)
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        (enemy,) = CharacterEnemy.objects.filter(character=character.sheet_data)
        self.assertEqual(enemy.organization, self.rivals)
        self.assertEqual(enemy.price, HOUSE_THWARTED_PRICE)

    def test_finalize_writes_no_enemy_for_a_draft_without_the_card(self) -> None:
        self._save_the_enemy()
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        self.assertFalse(CharacterEnemy.objects.filter(character=character.sheet_data).exists())


class TheCardsPickedOnIdentity(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.room = self.make_room("The Mirror Gallery")
        self.player = self.make_player("Odile", room=self.room)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Identity", height_min=700, height_max=800)
        self.indolent = DistinctionFactory(name="Indolent", cost_per_rank=5, max_rank=1)
        self.indolent_offer = DistinctionOfferFactory(
            distinction=self.indolent,
            chapter=OfferChapter.IDENTITY,
            arrives_as=OfferArrival.CHOICE,
            group="Temperament",
        )
        # A line staff switched off is not listed.
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Tireless"),
            chapter=OfferChapter.IDENTITY,
            is_active=False,
        )
        self.draft = self._create_base_draft(first_name="Odile")
        self.client = self.api(self.account)

    def _draft_url(self) -> str:
        return f"/api/character-creation/drafts/{self.draft.pk}/"

    def test_an_identity_card_is_listed_taken_and_held_on_the_sheet(self) -> None:
        response = self.client.get(IDENTITY_URL.format(pk=self.draft.pk))
        self.assertEqual(response.status_code, 200, response.content)
        (line,) = response.json()["offers"]
        self.assertEqual(line["name"], "Indolent")
        self.assertEqual(line["group"], "Temperament")
        self.assertEqual(line["opener_label"], "Identity")
        self.assertEqual(line["cost_per_rank"], 5)

        before = self.client.get(self._draft_url()).json()["cg_points_spent"]
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.indolent.pk, "rank": 1, "offer_id": self.indolent_offer.pk}
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [e["distinction_name"] for e in response.json()["distinctions"]], ["Indolent"]
        )
        after = self.client.get(self._draft_url()).json()["cg_points_spent"]
        self.assertEqual(after, before + 5)

        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        held = CharacterDistinction.objects.filter(character=character.sheet_data)
        self.assertEqual([row.distinction.name for row in held], ["Indolent"])
