from django.test import TestCase

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
    TraditionStateLineFactory,
)
from world.character_creation.offers import (
    closed_for,
    offers_for,
    reconcile_offer_picks,
    slate_state,
)
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory, TraditionFactory


class OffersForTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.scar = DistinctionFactory(name="Magical Scar", cost_per_rank=5, max_rank=3)
        cls.mark = GlimpseTagFactory(name="Mark")
        cls.loss = GlimpseTagFactory(name="Loss")
        cls.scar_offer = DistinctionOfferFactory(
            distinction=cls.scar, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.mark
        )
        cls.poor = DistinctionFactory(name="Impoverished", cost_per_rank=-25)
        cls.poor_offer = DistinctionOfferFactory(
            distinction=cls.poor, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.loss
        )

    def _draft(self, **data):
        return CharacterDraftFactory(
            account=self.account, selected_beginnings=self.beginning, draft_data=data
        )

    def test_glimpse_offers_open_with_their_tag_only(self):
        draft = self._draft(glimpse_tag_ids=[self.mark.id])
        offers = offers_for(draft, OfferChapter.GLIMPSE)
        assert [o.offer_id for o in offers] == [self.scar_offer.id]
        assert offers[0].opener_label == "Mark"
        assert offers[0].max_rank == 3

    def test_appearance_offers_need_no_opener(self):
        blood = DistinctionFactory(name="Giant's Blood", cost_per_rank=20)
        offer = DistinctionOfferFactory(distinction=blood, chapter=OfferChapter.APPEARANCE)
        draft = self._draft()
        assert [o.offer_id for o in offers_for(draft, OfferChapter.APPEARANCE)] == [offer.id]

    def test_route_closed_offers_are_hidden_and_listed(self):
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)
        draft = self._draft(glimpse_tag_ids=[self.mark.id])
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        assert offers_for(draft, OfferChapter.GLIMPSE) == []
        closed = closed_for(draft)
        assert [(c.distinction_id, c.reason) for c in closed] == [(self.scar.id, "Not here.")]

    def test_mutual_exclusion_locks_with_reason(self):
        other = DistinctionFactory(name="Other")
        self.scar.mutually_exclusive_with.add(other)
        draft = self._draft(
            glimpse_tag_ids=[self.mark.id],
            distinctions=[
                {
                    "distinction_id": other.id,
                    "rank": 1,
                    "cost": 0,
                    "distinction_name": "Other",
                    "distinction_slug": other.slug,
                    "category_slug": other.category.slug,
                    "notes": "",
                    "offer_ids": [],
                    "sources": [],
                    "arrivals": [],
                }
            ],
        )
        offer = offers_for(draft, OfferChapter.GLIMPSE)[0]
        assert offer.is_locked
        assert "Other" in offer.lock_reason


class SlateStateTests(TestCase):
    def test_returns_the_slate_lines_state(self):
        beginning = BeginningsFactory()
        tradition = TraditionFactory(name="Vigil")
        BeginningTraditionFactory(
            beginning=beginning, tradition=tradition, state=TraditionState.TEACHERS_GONE
        )
        assert slate_state(beginning, tradition) == TraditionState.TEACHERS_GONE

    def test_none_when_tradition_not_on_the_slate(self):
        beginning = BeginningsFactory()
        tradition = TraditionFactory(name="Elsewhere")
        assert slate_state(beginning, tradition) is None


class ReconcileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.unbound_drawback = DistinctionFactory(name="Unbound", cost_per_rank=-75)
        TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT,
            carries=cls.unbound_drawback,
            entry_line="Self-taught",
        )
        TraditionStateLineFactory(state=TraditionState.LIVING_MASTERS, entry_line="Living")
        cls.unbound = TraditionFactory(name="T1")
        cls.vigil = TraditionFactory(name="T2")
        BeginningTraditionFactory(
            beginning=cls.beginning, tradition=cls.unbound, state=TraditionState.SELF_TAUGHT
        )
        BeginningTraditionFactory(beginning=cls.beginning, tradition=cls.vigil)
        cls.poor = DistinctionFactory(name="Impoverished", cost_per_rank=-25)
        cls.route = OriginTemplateFactory(beginning=cls.beginning)
        cls.slot = OriginTemplateSlotFactory(template=cls.route, allows_text=False)
        cls.ran = OriginTemplateSlotChoiceFactory(slot=cls.slot, name="Ran")
        cls.bundle = DistinctionOfferFactory(
            distinction=cls.poor,
            chapter=OfferChapter.LINEAGE,
            origin_choice=cls.ran,
            arrives_as=OfferArrival.BUNDLED,
        )

    def _draft(self, **data):
        return CharacterDraftFactory(
            account=self.account, selected_beginnings=self.beginning, draft_data=data
        )

    def _ids(self, draft):
        return {d["distinction_id"]: d for d in draft.draft_data.get("distinctions", [])}

    def test_self_taught_tradition_carries_its_drawback_and_leaves_with_it(self):
        draft = self._draft()
        draft.selected_tradition = self.unbound
        draft.save(update_fields=["selected_tradition"])
        reconcile_offer_picks(draft)
        entry = self._ids(draft)[self.unbound_drawback.id]
        assert entry["cost"] == -75
        assert entry["arrivals"] == ["carried"]
        draft.selected_tradition = self.vigil
        draft.save(update_fields=["selected_tradition"])
        dropped = reconcile_offer_picks(draft)
        assert self.unbound_drawback.id not in self._ids(draft)
        assert dropped == ["Unbound"]

    def test_bundled_answer_adds_free_and_a_second_source_keeps_one_row(self):
        draft = self._draft(origin_choices={str(self.slot.id): self.ran.id})
        draft.selected_origin_template = self.route
        draft.save(update_fields=["selected_origin_template"])
        reconcile_offer_picks(draft)
        entry = self._ids(draft)[self.poor.id]
        assert entry["cost"] == 0
        assert entry["offer_ids"] == [self.bundle.id]
        # a Glimpse pick of the same distinction becomes a second source, not a row
        loss = GlimpseTagFactory(name="Loss")
        choice = DistinctionOfferFactory(
            distinction=self.poor, chapter=OfferChapter.GLIMPSE, glimpse_tag=loss
        )
        draft.draft_data["glimpse_tag_ids"] = [loss.id]
        entry["offer_ids"].append(choice.id)
        entry["sources"].append("Loss")
        entry["arrivals"].append("choice")
        draft.save(update_fields=["draft_data"])
        reconcile_offer_picks(draft)
        entries = draft.draft_data["distinctions"]
        assert len(entries) == 1
        assert entries[0]["cost"] == 0
        # the answer changes: the bundled source leaves, the Glimpse pick stays, priced
        draft.draft_data["origin_choices"] = {}
        draft.save(update_fields=["draft_data"])
        reconcile_offer_picks(draft)
        entry = self._ids(draft)[self.poor.id]
        assert entry["offer_ids"] == [choice.id]
        assert entry["cost"] == -25

    def test_legacy_entry_with_no_offer_ids_key_survives_unchanged(self):
        """A pre-#3675 pick (no offer_ids key at all) is left exactly as stored.

        Drafts saved before the offers system landed (0106) hold catalogue picks a
        player can no longer re-make -- there is no offer to trace such a pick back
        to. Review round 2 ruling A: this is a legacy entry, not a source that
        "vanished," so it is neither dropped nor repriced nor given the key.
        """
        legacy = DistinctionFactory(name="Old Family Ring", cost_per_rank=10)
        legacy_entry = {
            "distinction_id": legacy.id,
            "distinction_name": legacy.name,
            "distinction_slug": legacy.slug,
            "category_slug": legacy.category.slug,
            "rank": 1,
            "cost": 10,
            "notes": "",
        }
        draft = self._draft(distinctions=[dict(legacy_entry)])
        reconcile_offer_picks(draft)
        entry = self._ids(draft)[legacy.id]
        assert entry == legacy_entry
        assert "offer_ids" not in entry

    def test_legacy_entry_gains_a_bundled_source_for_the_same_distinction(self):
        """A legacy pick (no offer_ids) merges with a live bundled offer, not duplicates.

        Review round 2's ``_apply_bundled`` fix: when a legacy entry (see
        ``test_legacy_entry_with_no_offer_ids_key_survives_unchanged``) shares a
        distinction with an answer the draft now holds that bundles the same
        distinction, ``_apply_bundled``'s ``setdefault`` must extend that entry in
        place rather than crashing on a missing ``offer_ids`` key -- one row
        survives, carrying the new bundled source.
        """
        legacy_entry = {
            "distinction_id": self.poor.id,
            "distinction_name": self.poor.name,
            "distinction_slug": self.poor.slug,
            "category_slug": self.poor.category.slug,
            "rank": 1,
            "cost": -25,
            "notes": "",
        }
        draft = self._draft(
            distinctions=[dict(legacy_entry)],
            origin_choices={str(self.slot.id): self.ran.id},
        )
        draft.selected_origin_template = self.route
        draft.save(update_fields=["selected_origin_template"])

        reconcile_offer_picks(draft)

        entries = draft.draft_data["distinctions"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["distinction_id"] == self.poor.id
        assert entry["offer_ids"] == [self.bundle.id]
        assert entry["sources"] == ["Ran"]
        assert entry["arrivals"] == [OfferArrival.BUNDLED]
        assert entry["cost"] == 0
