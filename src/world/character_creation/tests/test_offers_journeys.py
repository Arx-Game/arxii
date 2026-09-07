"""Journey tests over the draft REST seam, end to end (#3675 Task 18).

Six journeys from the spec's Testing section, each driven through the actual
API surface a player's browser hits (offers GET, draft PATCH, distinctions
sync PUT) and, where the journey says so, through ``finalize_character`` to
prove the rows an approved character actually gets. Builds on the same
factories ``test_offers.py``/``test_offers_api.py``/``test_offers_models.py``
use, and ``finalization_fixtures.FinalizationTestMixin`` for the three
journeys that finalize a character.

Every distinction/offer/tradition-state row a test asserts against comes from
a factory the test itself holds -- never a name lookup.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferArrival, OfferChapter, TraditionState
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
    SchoolingLineFactory,
    TraditionStateLineFactory,
)
from world.character_creation.offers import self_taught_drawback
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import GlimpseTagAxis
from world.magic.factories import GlimpseTagFactory, TraditionFactory, TraditionGiftGrantFactory
from world.magic.models import CharacterAura
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory


class TraditionStepJourneyTests(FinalizationTestMixin, TestCase):
    """Journey 1 (tradition step end to end) and journey 2 (state switches)."""

    @classmethod
    def setUpTestData(cls):
        cls._setup_finalization_base(
            cls, prefix="Tradition Journey", height_min=1600, height_max=1700
        )

        # Journey 1: a LIVING_MASTERS tradition with three schooling lines.
        cls.living_tradition = TraditionFactory()
        BeginningTraditionFactory(
            beginning=cls.beginnings,
            tradition=cls.living_tradition,
            state=TraditionState.LIVING_MASTERS,
        )
        TraditionGiftGrantFactory(tradition=cls.living_tradition, gift=cls.gift)

        cls.line0_dist = DistinctionFactory(name="Novice Stance", cost_per_rank=2, max_rank=1)
        cls.line0 = SchoolingLineFactory(
            rank=0, name="Novice", player_line="Barely begun.", grants=cls.line0_dist
        )
        cls.line0_offer = DistinctionOfferFactory(
            distinction=cls.line0_dist,
            chapter=OfferChapter.TRADITION_STEP,
            schooling_line=cls.line0,
        )

        cls.line1_dist = DistinctionFactory(name="Journeyman Stance", cost_per_rank=3, max_rank=1)
        cls.line1 = SchoolingLineFactory(
            rank=1, name="Journeyman", player_line="Steady hands.", grants=cls.line1_dist
        )
        cls.line1_offer = DistinctionOfferFactory(
            distinction=cls.line1_dist,
            chapter=OfferChapter.TRADITION_STEP,
            schooling_line=cls.line1,
        )

        cls.line2_dist = DistinctionFactory(name="Master Stance", cost_per_rank=4, max_rank=2)
        cls.line2 = SchoolingLineFactory(
            rank=2, name="Master", player_line="Years of it.", grants=cls.line2_dist
        )
        cls.line2_offer = DistinctionOfferFactory(
            distinction=cls.line2_dist,
            chapter=OfferChapter.TRADITION_STEP,
            schooling_line=cls.line2,
        )

        # Journey 2: TEACHERS_GONE and SELF_TAUGHT traditions on the same slate.
        cls.gone_tradition = TraditionFactory()
        cls.gone_drawback = DistinctionFactory(name="Orphaned Stances", cost_per_rank=-30)
        cls.gone_state_line = TraditionStateLineFactory(
            state=TraditionState.TEACHERS_GONE,
            carries=cls.gone_drawback,
            entry_line="No masters remain to teach it.",
        )
        BeginningTraditionFactory(
            beginning=cls.beginnings,
            tradition=cls.gone_tradition,
            state=TraditionState.TEACHERS_GONE,
        )

        cls.self_tradition = TraditionFactory()
        cls.self_drawback = DistinctionFactory(name="Unbound", cost_per_rank=-75)
        cls.self_state_line = TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT,
            carries=cls.self_drawback,
            entry_line="No one ever taught you.",
        )
        BeginningTraditionFactory(
            beginning=cls.beginnings,
            tradition=cls.self_tradition,
            state=TraditionState.SELF_TAUGHT,
        )
        TraditionGiftGrantFactory(tradition=cls.self_tradition, gift=cls.gift)

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"tradition_journey_{id(self)}")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _draft(self):
        return self._create_base_draft(first_name="TraditionJourney")

    def test_tradition_step_offers_pick_and_finalize(self):
        """Journey 1: three schooling lines offered, rank-2 pick, finalize writes it."""
        draft = self._draft()

        select_resp = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.living_tradition.id},
            format="json",
        )
        assert select_resp.status_code == status.HTTP_200_OK

        offers_resp = self.client.get(
            f"/api/character-creation/drafts/{draft.id}/offers/?chapter=tradition_step"
        )
        assert offers_resp.status_code == status.HTTP_200_OK
        assert offers_resp.data["closed"] == []
        rows_by_offer = {row["offer_id"]: row for row in offers_resp.data["offers"]}
        assert set(rows_by_offer) == {
            self.line0_offer.id,
            self.line1_offer.id,
            self.line2_offer.id,
        }
        for line, offer, dist in (
            (self.line0, self.line0_offer, self.line0_dist),
            (self.line1, self.line1_offer, self.line1_dist),
            (self.line2, self.line2_offer, self.line2_dist),
        ):
            row = rows_by_offer[offer.id]
            assert row["cost_per_rank"] == dist.cost_per_rank
            assert row["max_rank"] == dist.max_rank
            assert row["opener_label"] == line.name
            # The line's own price is derived from the distinction it grants
            # (SchoolingLine.price), never a stored literal on the offer or line.
            assert line.price == dist.cost_per_rank * line.rank

        sync_resp = self.client.put(
            f"/api/distinctions/drafts/{draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.line2_dist.id, "rank": 2, "offer_id": self.line2_offer.id}
                ]
            },
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        (entry,) = draft.draft_data["distinctions"]
        assert entry["distinction_id"] == self.line2_dist.id
        assert entry["rank"] == 2
        assert entry["cost"] == self.line2_dist.cost_per_rank * 2
        assert entry["sources"] == [self.line2.name]
        assert entry["offer_ids"] == [self.line2_offer.id]

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        cd = CharacterDistinction.objects.get(character=sheet, distinction=self.line2_dist)
        assert cd.rank == 2
        assert cd.source_description == self.line2.name
        assert cd.origin == DistinctionOrigin.CHARACTER_CREATION

    def test_tradition_switch_carries_teachers_gone_then_self_taught(self):
        """Journey 2: switching tradition drops the schooling pick, carries the state's
        drawback, refunds the schooling price, and finalize records the self-taught row."""
        draft = self._draft()

        self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.living_tradition.id},
            format="json",
        )
        sync_resp = self.client.put(
            f"/api/distinctions/drafts/{draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.line2_dist.id, "rank": 2, "offer_id": self.line2_offer.id}
                ]
            },
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        schooling_cost = self.line2_dist.cost_per_rank * 2
        remaining_before = draft.calculate_cg_points_remaining()

        gone_resp = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.gone_tradition.id},
            format="json",
        )
        assert gone_resp.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        entries_by_id = {e["distinction_id"]: e for e in draft.draft_data["distinctions"]}
        assert self.line2_dist.id not in entries_by_id
        gone_entry = entries_by_id[self.gone_drawback.id]
        assert gone_entry["arrivals"] == [OfferArrival.CARRIED]
        assert gone_entry["offer_ids"] == [f"state:{TraditionState.TEACHERS_GONE}"]
        assert gone_entry["sources"] == [self.gone_state_line.entry_line]
        assert gone_entry["cost"] == self.gone_drawback.cost_per_rank
        # The purse refunds the schooling price: the schooling entry's cost is
        # gone and the carried drawback's own cost (a refund, being negative)
        # is the only other change to what's spent.
        remaining_after_gone = draft.calculate_cg_points_remaining()
        assert remaining_after_gone == (
            remaining_before + schooling_cost - self.gone_drawback.cost_per_rank
        )

        self_resp = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.self_tradition.id},
            format="json",
        )
        assert self_resp.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        entries_by_id = {e["distinction_id"]: e for e in draft.draft_data["distinctions"]}
        assert self.gone_drawback.id not in entries_by_id
        self_entry = entries_by_id[self.self_drawback.id]
        assert self_entry["arrivals"] == [OfferArrival.CARRIED]
        assert self_entry["offer_ids"] == [f"state:{TraditionState.SELF_TAUGHT}"]
        assert self_entry["sources"] == [self.self_state_line.entry_line]

        # Read offers.py's own resolvers rather than assuming a name: the row
        # finalize writes is whatever they say it is.
        assert self_taught_drawback() == self.self_drawback

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        cd = CharacterDistinction.objects.get(character=sheet, distinction=self.self_drawback)
        assert cd.rank == 1
        assert cd.source_description == self.self_state_line.entry_line
        assert cd.origin == DistinctionOrigin.CHARACTER_CREATION
        assert (
            CharacterDistinction.objects.filter(
                character=sheet, distinction=self.gone_drawback
            ).exists()
            is False
        )


class GlimpseJourneyTests(FinalizationTestMixin, TestCase):
    """Journey 3: Glimpse tags, a ranked pick, a closed distinction, from_glimpse at finalize."""

    @classmethod
    def setUpTestData(cls):
        cls._setup_finalization_base(
            cls, prefix="Glimpse Journey", height_min=1600, height_max=1700
        )

        cls.mark = GlimpseTagFactory(name="Mark", axis=GlimpseTagAxis.TONE)
        cls.loss = GlimpseTagFactory(name="Loss", axis=GlimpseTagAxis.CONSEQUENCE)
        cls.public = GlimpseTagFactory(name="Public", axis=GlimpseTagAxis.WITNESS)

        cls.mark_dist = DistinctionFactory(name="Scar Mark", cost_per_rank=5, max_rank=1)
        cls.mark_offer = DistinctionOfferFactory(
            distinction=cls.mark_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.mark
        )
        cls.loss_dist = DistinctionFactory(name="Grief Debt", cost_per_rank=-10, max_rank=1)
        cls.loss_offer = DistinctionOfferFactory(
            distinction=cls.loss_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.loss
        )
        cls.public_dist = DistinctionFactory(name="Known Face", cost_per_rank=8, max_rank=3)
        cls.public_offer = DistinctionOfferFactory(
            distinction=cls.public_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.public
        )

        cls.highborn = DistinctionFactory(name="Highborn", cost_per_rank=15, max_rank=1)
        cls.highborn_offer = DistinctionOfferFactory(
            distinction=cls.highborn, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.public
        )
        cls.route = OriginTemplateFactory(
            beginning=cls.beginnings,
            closed_reason="Not for this line.",
            allows_name_family=False,
            allows_no_family=True,
        )
        cls.route.closed_distinctions.add(cls.highborn)

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"glimpse_journey_{id(self)}")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_glimpse_offers_picks_closed_and_finalize_links_from_glimpse(self):
        draft = self._create_base_draft(
            first_name="GlimpseJourney",
            glimpse_tag_ids=[self.mark.id, self.loss.id, self.public.id],
        )
        draft.selected_origin_template = self.route
        draft.save(update_fields=["selected_origin_template"])

        offers_resp = self.client.get(
            f"/api/character-creation/drafts/{draft.id}/offers/?chapter=glimpse"
        )
        assert offers_resp.status_code == status.HTTP_200_OK
        offer_ids = {row["offer_id"] for row in offers_resp.data["offers"]}
        assert offer_ids == {self.mark_offer.id, self.loss_offer.id, self.public_offer.id}
        assert self.highborn_offer.id not in offer_ids
        (closed,) = offers_resp.data["closed"]
        assert closed["distinction_id"] == self.highborn.id
        assert closed["reason"] == self.route.closed_reason
        assert closed["opener_labels"] == [self.public.name]

        sync_resp = self.client.put(
            f"/api/distinctions/drafts/{draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.mark_dist.id, "rank": 1, "offer_id": self.mark_offer.id},
                    {"id": self.loss_dist.id, "rank": 1, "offer_id": self.loss_offer.id},
                    {"id": self.public_dist.id, "rank": 2, "offer_id": self.public_offer.id},
                ]
            },
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        entries_by_id = {e["distinction_id"]: e for e in draft.draft_data["distinctions"]}
        assert entries_by_id[self.public_dist.id]["rank"] == 2
        assert entries_by_id[self.mark_dist.id]["rank"] == 1
        assert entries_by_id[self.loss_dist.id]["rank"] == 1

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        aura = CharacterAura.objects.get(character=sheet)
        for dist in (self.mark_dist, self.loss_dist, self.public_dist):
            cd = CharacterDistinction.objects.get(character=sheet, distinction=dist)
            assert cd.from_glimpse_id == aura.pk


class UpbringingBundleAndOfferJourneyTests(TestCase):
    """Journey 4: an answer that bundles one distinction and offers another."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.route = OriginTemplateFactory(beginning=cls.beginning)
        cls.slot = OriginTemplateSlotFactory(template=cls.route, allows_text=False)
        cls.choice = OriginTemplateSlotChoiceFactory(slot=cls.slot, name="Ran with the yard dogs")

        cls.bundled_dist = DistinctionFactory(name="Yard Grit", cost_per_rank=6, max_rank=1)
        cls.bundle_offer = DistinctionOfferFactory(
            distinction=cls.bundled_dist,
            chapter=OfferChapter.LINEAGE,
            origin_choice=cls.choice,
            arrives_as=OfferArrival.BUNDLED,
        )
        cls.offered_dist = DistinctionFactory(name="Quick Hands", cost_per_rank=4, max_rank=1)
        cls.offered_offer = DistinctionOfferFactory(
            distinction=cls.offered_dist,
            chapter=OfferChapter.LINEAGE,
            origin_choice=cls.choice,
            arrives_as=OfferArrival.CHOICE,
        )

        cls.glimpse_tag = GlimpseTagFactory(name="Loyalty")
        cls.glimpse_dist = DistinctionFactory(name="Sworn Word", cost_per_rank=3, max_rank=1)
        cls.glimpse_offer = DistinctionOfferFactory(
            distinction=cls.glimpse_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.glimpse_tag
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            selected_origin_template=self.route,
        )

    def test_bundled_and_offered_answer_then_the_answer_changes(self):
        url = f"/api/character-creation/drafts/{self.draft.id}/"

        pick_resp = self.client.patch(
            url,
            {"draft_data": {"origin_choices": {str(self.slot.id): self.choice.id}}},
            format="json",
        )
        assert pick_resp.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        (bundled_entry,) = self.draft.draft_data["distinctions"]
        assert bundled_entry["distinction_id"] == self.bundled_dist.id
        assert bundled_entry["arrivals"] == [OfferArrival.BUNDLED]
        assert bundled_entry["cost"] == 0

        offers_resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=lineage"
        )
        assert offers_resp.status_code == status.HTTP_200_OK
        offer_ids = {row["offer_id"] for row in offers_resp.data["offers"]}
        assert offer_ids == {self.offered_offer.id}

        tag_resp = self.client.patch(
            url, {"draft_data": {"glimpse_tag_ids": [self.glimpse_tag.id]}}, format="json"
        )
        assert tag_resp.status_code == status.HTTP_200_OK

        sync_resp = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.offered_dist.id, "rank": 1, "offer_id": self.offered_offer.id},
                    {"id": self.glimpse_dist.id, "rank": 1, "offer_id": self.glimpse_offer.id},
                ]
            },
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        ids = {e["distinction_id"] for e in self.draft.draft_data["distinctions"]}
        assert ids == {self.bundled_dist.id, self.offered_dist.id, self.glimpse_dist.id}

        change_resp = self.client.patch(url, {"draft_data": {"origin_choices": {}}}, format="json")
        assert change_resp.status_code == status.HTTP_200_OK
        self.draft.refresh_from_db()
        remaining_ids = {e["distinction_id"] for e in self.draft.draft_data["distinctions"]}
        # Both the bundled and the offered pick leave (their opener is gone);
        # the Glimpse pick, unrelated to the answer, stays.
        assert remaining_ids == {self.glimpse_dist.id}


class SyncRejectionJourneyTests(TestCase):
    """Journey 5: sync rejects an unearned offer; a legacy entry is left untouched."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.open_tag = GlimpseTagFactory(name="Open Door")
        cls.hidden_tag = GlimpseTagFactory(name="Shut Door")
        cls.hidden_dist = DistinctionFactory(name="Locked Away", cost_per_rank=5, max_rank=1)
        cls.hidden_offer = DistinctionOfferFactory(
            distinction=cls.hidden_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.hidden_tag
        )
        cls.legacy_dist = DistinctionFactory(name="Family Locket", cost_per_rank=10, max_rank=1)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.legacy_entry = {
            "distinction_id": self.legacy_dist.id,
            "distinction_name": self.legacy_dist.name,
            "distinction_slug": self.legacy_dist.slug,
            "category_slug": self.legacy_dist.category.slug,
            "rank": 1,
            "cost": 10,
            "notes": "",
        }
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            draft_data={
                "glimpse_tag_ids": [self.open_tag.id],
                "distinctions": [dict(self.legacy_entry)],
            },
        )

    def test_sync_rejects_unearned_offer_and_leaves_legacy_entry_untouched(self):
        resp = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.hidden_dist.id, "rank": 1, "offer_id": self.hidden_offer.id}
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert self.hidden_dist.name in resp.data["detail"]
        assert self.hidden_tag.name in resp.data["detail"]

        self.draft.refresh_from_db()
        assert self.draft.draft_data["distinctions"] == [self.legacy_entry]
        assert "offer_ids" not in self.draft.draft_data["distinctions"][0]


class InnateExclusionJourneyTests(TestCase):
    """Journey 6 (the plan's addition): a species-innate distinction is never offered
    twice, and sync refuses to add it as a choice."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.species = SpeciesFactory()
        cls.innate_dist = DistinctionFactory(name="Iron Skin", cost_per_rank=5, max_rank=1)
        SpeciesGiftGrantFactory(species=cls.species, drawback_distinction=cls.innate_dist)
        cls.tag = GlimpseTagFactory(name="Forged")
        cls.offer = DistinctionOfferFactory(
            distinction=cls.innate_dist, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.tag
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            selected_species=self.species,
            draft_data={"glimpse_tag_ids": [self.tag.id]},
        )

    def test_innate_distinction_is_hidden_from_offers_and_sync_rejects_it(self):
        offers_resp = self.client.get(
            f"/api/character-creation/drafts/{self.draft.id}/offers/?chapter=glimpse"
        )
        assert offers_resp.status_code == status.HTTP_200_OK
        assert offers_resp.data["offers"] == []

        sync_resp = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {"distinctions": [{"id": self.innate_dist.id, "rank": 1, "offer_id": self.offer.id}]},
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "innate" in sync_resp.data["detail"].lower()

        self.draft.refresh_from_db()
        assert self.draft.draft_data.get("distinctions", []) == []
