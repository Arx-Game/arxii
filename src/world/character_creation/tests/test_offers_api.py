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
from world.magic.factories import GlimpseTagFactory, TraditionFactory


class OffersEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.mark = GlimpseTagFactory(name="Mark")
        cls.scar = DistinctionFactory(name="Magical Scar", cost_per_rank=5, max_rank=3)
        cls.offer = DistinctionOfferFactory(
            distinction=cls.scar,
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=cls.mark,
            player_line="A scar that answers magic.",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            draft_data={"glimpse_tag_ids": [self.mark.id]},
        )

    def test_lists_the_chapter_offers_the_draft_earned(self):
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=glimpse"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["closed"] == []
        (row,) = resp.data["offers"]
        assert row["offer_id"] == self.offer.id
        assert row["player_line"] == "A scar that answers magic."
        assert row["max_rank"] == 3
        assert row["cost_per_rank"] == 5

    def test_closed_distinctions_carry_opener_labels_scoped_to_the_chapter(self):
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)
        self.draft.selected_origin_template = route
        self.draft.save(update_fields=["selected_origin_template"])
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=glimpse"
        )
        assert resp.status_code == status.HTTP_200_OK
        (closed,) = resp.data["closed"]
        assert closed["opener_labels"] == ["Mark"]
        # B4 (#3675 final fix): the offer ids behind those labels, index-aligned,
        # so a caller can match a closed row to a specific offer without a
        # name/label match.
        assert closed["opener_ids"] == [self.offer.id]

    def test_rejects_an_unknown_chapter(self):
        resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=nope"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_sync_accepts_an_offer_and_rejects_an_unearned_one(self):
        loss = GlimpseTagFactory(name="Loss")
        poor = DistinctionFactory(name="Impoverished", cost_per_rank=-25)
        hidden = DistinctionOfferFactory(
            distinction=poor, chapter=OfferChapter.GLIMPSE, glimpse_tag=loss
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
