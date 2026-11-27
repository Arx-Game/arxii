from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    OriginTemplateFactory,
    TraditionStateLineFactory,
)
from world.distinctions.factories import DistinctionFactory
from world.magic.constants import GlimpseTagAxis
from world.magic.factories import GlimpseTagFactory, TraditionFactory


class OffersEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.scar = DistinctionFactory(name="Magical Scar", cost_per_rank=5, max_rank=3)
        cls.offer = DistinctionOfferFactory(
            distinction=cls.scar,
            chapter=OfferChapter.APPEARANCE,
            player_line="A scar that answers magic.",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            draft_data={},
        )

    def test_lists_the_chapter_offers_the_draft_earned(self):
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=appearance"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "closed" not in resp.data
        (row,) = resp.data["offers"]
        assert row["offer_id"] == self.offer.id
        assert row["player_line"] == "A scar that answers magic."
        assert row["max_rank"] == 3
        assert row["cost_per_rank"] == 5
        assert resp.data["glimpse_cards"] == []

    def test_the_glimpse_chapter_lists_no_choice_and_reports_the_cards_it_gave(self):
        """#5292: a Glimpse card comes free with its answer, so the chapter has nothing
        to pick; the cards the draft's answers gave are reported for the stage's panel."""
        from world.distinctions.factories import DistinctionEffectFactory
        from world.mechanics.factories import ModifierTargetFactory

        wonder = GlimpseTagFactory(name="Wonder")
        struck = DistinctionFactory(name="Wonderstruck", cost_per_rank=20)
        DistinctionEffectFactory(
            distinction=struck, target=ModifierTargetFactory(name="anima"), value_per_rank=1
        )
        line = DistinctionOfferFactory(
            distinction=struck, chapter=OfferChapter.GLIMPSE, glimpse_tag=wonder
        )
        self.draft.draft_data = {"glimpse_tag_ids": [wonder.id]}
        self.draft.save(update_fields=["draft_data"])
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=glimpse"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["offers"] == []
        assert resp.data["glimpse_cards"] == [
            {
                "offer_id": line.id,
                "distinction_id": struck.id,
                "name": "Wonderstruck",
                "source": "Wonder",
                "axis": "TONE",
                "effect_line": "+Anima",
            }
        ]

    def test_saving_a_glimpse_answer_holds_its_card_free_in_the_same_response(self):
        """#5292: the draft save that carries the answer returns the card held, at no
        price, and the CG points do not move."""
        wonder = GlimpseTagFactory(name="Wonder")
        struck = DistinctionFactory(name="Wonderstruck", cost_per_rank=20)
        DistinctionOfferFactory(
            distinction=struck, chapter=OfferChapter.GLIMPSE, glimpse_tag=wonder
        )
        url = f"/api/character-creation/drafts/{self.draft.id}/"
        before = self.client.get(url).data["cg_points_remaining"]
        resp = self.client.patch(
            url, {"draft_data": {"glimpse_tag_ids": [wonder.id]}}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        (entry,) = resp.data["draft_data"]["distinctions"]
        assert entry["distinction_name"] == "Wonderstruck"
        assert entry["cost"] == 0
        assert resp.data["cg_points_remaining"] == before
        cleared = self.client.patch(url, {"draft_data": {"glimpse_tag_ids": []}}, format="json")
        assert cleared.data["draft_data"]["distinctions"] == []
        assert cleared.data["cg_points_remaining"] == before

    def test_a_save_with_two_answers_in_one_part_is_refused(self):
        """#5292: every part takes one answer, tried on a part that gives a card and on
        one that gives none."""
        url = f"/api/character-creation/drafts/{self.draft.id}/"
        for axis, label in (
            (GlimpseTagAxis.REFLECTION, "The Reflection"),
            (GlimpseTagAxis.WITNESS, "Witness & Secrecy"),
        ):
            first = GlimpseTagFactory(axis=axis)
            second = GlimpseTagFactory(axis=axis)
            resp = self.client.patch(
                url, {"draft_data": {"glimpse_tag_ids": [first.id, second.id]}}, format="json"
            )
            with self.subTest(axis=axis):
                assert resp.status_code == status.HTTP_400_BAD_REQUEST
                assert f"{label} takes one answer." in str(resp.data)
        self.draft.refresh_from_db()
        assert "glimpse_tag_ids" not in self.draft.draft_data

    def test_an_unknown_memory_state_is_refused(self):
        url = f"/api/character-creation/drafts/{self.draft.id}/"
        resp = self.client.patch(url, {"draft_data": {"glimpse_memory": "forgot"}}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_route_closed_distinction_is_absent_from_the_payload(self):
        """#4979: the offers payload leaves a route-closed card out and names it nowhere."""
        route = OriginTemplateFactory(beginning=self.beginning)
        route.closed_distinctions.add(self.scar)
        self.draft.selected_origin_template = route
        self.draft.save(update_fields=["selected_origin_template"])
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=appearance"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["offers"] == []
        assert "closed" not in resp.data

    def test_rejects_an_unknown_chapter(self):
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=nope"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_sync_accepts_an_offer_and_rejects_an_unearned_one(self):
        poor = DistinctionFactory(name="Impoverished", cost_per_rank=-25)
        # Unearned: a Final Touches line shows only to a draft holding the card that
        # unlocks it, and this draft does not.
        hidden = DistinctionOfferFactory(
            distinction=poor,
            chapter=OfferChapter.FINAL_TOUCHES,
            unlocked_by=DistinctionFactory(name="Loss"),
        )
        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        ok = self.client.put(
            url,
            {"distinctions": [{"id": self.scar.id, "rank": 2, "offer_id": self.offer.id}]},
            format="json",
        )
        assert ok.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        (entry,) = self.draft.draft_data["distinctions"]
        assert entry["offer_ids"] == [self.offer.id]
        assert entry["cost"] == 10
        bad = self.client.put(
            url,
            {"distinctions": [{"id": poor.id, "rank": 1, "offer_id": hidden.id}]},
            format="json",
        )
        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert "Loss" in bad.data["detail"]

    def test_sync_without_an_offer_is_rejected_in_cg(self):
        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        resp = self.client.put(
            url, {"distinctions": [{"id": self.scar.id, "rank": 1}]}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_sync_merges_two_offers_for_the_same_distinction(self):
        offer_a = DistinctionOfferFactory(
            distinction=self.scar, chapter=OfferChapter.APPEARANCE, name="Old Wound"
        )
        offer_b = DistinctionOfferFactory(
            distinction=self.scar, chapter=OfferChapter.APPEARANCE, name="Battle Mark"
        )
        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        resp = self.client.put(
            url,
            {
                "distinctions": [
                    {"id": self.scar.id, "rank": 1, "offer_id": offer_a.id},
                    {"id": self.scar.id, "rank": 2, "offer_id": offer_b.id},
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        (entry,) = self.draft.draft_data["distinctions"]
        assert entry["rank"] == 2
        assert set(entry["offer_ids"]) == {offer_a.id, offer_b.id}
        assert len(entry["sources"]) == 2
        assert entry["cost"] == self.scar.cost_per_rank * 2


class SelectTraditionCarriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.drawback = DistinctionFactory(name="Unbound", cost_per_rank=-75)
        TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT, carries=cls.drawback, entry_line="Self-taught"
        )
        cls.tradition = TraditionFactory()
        BeginningTraditionFactory(
            beginning=cls.beginning, tradition=cls.tradition, state=TraditionState.SELF_TAUGHT
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(account=self.account, selected_beginnings=self.beginning)

    def test_selecting_a_self_taught_tradition_carries_the_drawback(self):
        resp = self.client.post(
            f"/api/character-creation/drafts/{self.draft.id}/select-tradition/",
            {"tradition_id": self.tradition.id},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        (entry,) = self.draft.draft_data["distinctions"]
        assert entry["distinction_id"] == self.drawback.id
        assert entry["cost"] == -75

    def test_clearing_the_tradition_removes_the_carried_drawback(self):
        url = f"/api/character-creation/drafts/{self.draft.id}/select-tradition/"
        self.client.post(url, {"tradition_id": self.tradition.id}, format="json")
        self.client.post(url, {"tradition_id": None}, format="json")
        self.draft.refresh_from_db()
        assert self.draft.draft_data.get("distinctions", []) == []

    def test_destroying_the_carried_drawback_entry_is_reverted_by_reconcile(self):
        self.client.post(
            f"/api/character-creation/drafts/{self.draft.id}/select-tradition/",
            {"tradition_id": self.tradition.id},
            format="json",
        )
        self.draft.refresh_from_db()
        (held,) = self.draft.draft_data["distinctions"]
        assert held["distinction_id"] == self.drawback.id

        resp = self.client.delete(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/{self.drawback.id}/"
        )
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        self.draft.refresh_from_db()
        (entry,) = self.draft.draft_data["distinctions"]
        assert entry["distinction_id"] == self.drawback.id
