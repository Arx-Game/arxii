from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferArrival, OfferChapter, TraditionState
from world.character_creation.factories import (
    AppearanceSectionFactory,
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    EnemyReasonFactory,
    OfferFirstLookFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
    TraditionStateLineFactory,
)
from world.character_creation.offers import (
    closed_for,
    degree_marks,
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

    def test_appearance_offers_hang_off_a_section(self):
        """An Appearance line is grouped by its section; one with none is not shown (#3709)."""
        blood = DistinctionFactory(name="Giant's Blood", cost_per_rank=20)
        frame = AppearanceSectionFactory(name="Frame")
        offer = DistinctionOfferFactory(
            distinction=blood, chapter=OfferChapter.APPEARANCE, appearance_section=frame
        )
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Unsectioned"),
            chapter=OfferChapter.APPEARANCE,
            appearance_section=None,
        )
        draft = self._draft()
        offers = offers_for(draft, OfferChapter.APPEARANCE)
        assert [o.offer_id for o in offers] == [offer.id]
        assert offers[0].opener_key == f"section:{frame.id}"
        assert offers[0].opener_label == "Frame"

    def test_actors_sheet_offers_hang_off_a_prompt(self):
        """Each actor's-sheet line names the question it answers (#3709)."""
        haunted = DistinctionFactory(name="Haunted", cost_per_rank=10)
        offer = DistinctionOfferFactory(
            distinction=haunted, chapter=OfferChapter.ACTORS_SHEET, prompt="fear"
        )
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Unprompted"),
            chapter=OfferChapter.ACTORS_SHEET,
            prompt="",
        )
        draft = self._draft()
        offers = offers_for(draft, OfferChapter.ACTORS_SHEET)
        assert [o.offer_id for o in offers] == [offer.id]
        assert offers[0].opener_key == "prompt:fear"
        assert offers[0].opener_label == "What are you deathly afraid of?"

    def test_first_look_pins_sort_first_and_the_rest_follow_sort_order(self):
        """The draft's Beginning pins a line into the first look (#3709)."""
        frame = AppearanceSectionFactory(name="Frame")
        first = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="First"),
            chapter=OfferChapter.APPEARANCE,
            appearance_section=frame,
            sort_order=10,
        )
        second = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Second"),
            chapter=OfferChapter.APPEARANCE,
            appearance_section=frame,
            sort_order=20,
        )
        third = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Third"),
            chapter=OfferChapter.APPEARANCE,
            appearance_section=frame,
            sort_order=30,
        )
        OfferFirstLookFactory(offer=third, beginning=self.beginning)
        OfferFirstLookFactory(offer=third, beginning=BeginningsFactory())  # another Beginning
        draft = self._draft()
        offers = offers_for(draft, OfferChapter.APPEARANCE)
        assert [o.offer_id for o in offers] == [third.id, first.id, second.id]
        assert [o.first_look for o in offers] == [True, False, False]

    def test_held_elsewhere_is_marked_and_the_effect_line_reads_signs(self):
        """A distinction already in the draft from another line reads held (#3709)."""
        from world.distinctions.factories import DistinctionEffectFactory
        from world.mechanics.factories import ModifierTargetFactory

        secretive = DistinctionFactory(name="Secretive", cost_per_rank=25)
        DistinctionEffectFactory(
            distinction=secretive,
            target=ModifierTargetFactory(name="deception"),
            value_per_rank=1,
        )
        DistinctionEffectFactory(
            distinction=secretive,
            target=ModifierTargetFactory(name="willpower"),
            value_per_rank=-1,
        )
        under_rules = DistinctionOfferFactory(
            distinction=secretive, chapter=OfferChapter.ACTORS_SHEET, prompt="never_do"
        )
        under_protect = DistinctionOfferFactory(
            distinction=secretive, chapter=OfferChapter.ACTORS_SHEET, prompt="protect"
        )
        draft = self._draft(
            distinctions=[
                {
                    "distinction_id": secretive.id,
                    "distinction_name": "Secretive",
                    "rank": 1,
                    "cost": 25,
                    "offer_ids": [under_rules.id],
                    "sources": ["What would you never do?"],
                    "arrivals": ["choice"],
                }
            ]
        )
        by_id = {o.offer_id: o for o in offers_for(draft, OfferChapter.ACTORS_SHEET)}
        assert by_id[under_rules.id].held is False
        assert by_id[under_protect.id].held is True
        assert by_id[under_rules.id].effect_line == "+Deception; -Willpower"

    def test_enemy_reason_opens_its_offers_and_the_degree_bundles_its_mark(self):
        """The enemy chapter's two openers: the picked reason, the picked degree (#3709)."""
        reason = EnemyReasonFactory(name="You know what they did")
        other = EnemyReasonFactory(name="You stole from them")
        sleeper = DistinctionFactory(name="Light Sleeper", cost_per_rank=-5)
        fingers = DistinctionFactory(name="Light Fingers", cost_per_rank=5)
        marked = DistinctionFactory(name="Marked", cost_per_rank=0)
        sleeper_offer = DistinctionOfferFactory(
            distinction=sleeper, chapter=OfferChapter.ENEMY, enemy_reason=reason
        )
        DistinctionOfferFactory(distinction=fingers, chapter=OfferChapter.ENEMY, enemy_reason=other)
        DistinctionOfferFactory(
            distinction=marked,
            chapter=OfferChapter.ENEMY,
            arrives_as=OfferArrival.BUNDLED,
            enemy_degree="ruined",
        )
        draft = self._draft(enemy={"kind": "group", "reason_id": reason.id, "degree": "ruined"})
        offers = offers_for(draft, OfferChapter.ENEMY)
        assert [o.offer_id for o in offers] == [sleeper_offer.id]
        assert offers[0].opener_key == f"reason:{reason.id}"
        assert degree_marks() == {"ruined": ["Marked"]}

        # The mark arrives as a bundle through the reconcile, and leaves with the degree.
        reconcile_offer_picks(draft)
        names = [e["distinction_name"] for e in draft.draft_data["distinctions"]]
        assert names == ["Marked"]
        draft.draft_data["enemy"]["degree"] = "thwarted"
        reconcile_offer_picks(draft)
        assert draft.draft_data["distinctions"] == []

    def test_route_closed_offers_are_hidden_and_listed(self):
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)
        draft = self._draft(glimpse_tag_ids=[self.mark.id])
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        assert offers_for(draft, OfferChapter.GLIMPSE) == []
        closed = closed_for(draft, OfferChapter.GLIMPSE)
        assert [(c.distinction_id, c.reason) for c in closed] == [(self.scar.id, "Not here.")]

    def test_closed_distinction_opener_labels_name_the_tag_that_would_have_opened_it(self):
        """The demo's "Highborn under Public" case (#3675 fix round 2): a closed
        distinction's ``opener_labels`` names the picked tag that would have
        opened it in this chapter, so the chapter mount can print the closed
        hint once, under that specific pick, instead of under every pick."""
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)
        draft = self._draft(glimpse_tag_ids=[self.mark.id])
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        (closed,) = closed_for(draft, OfferChapter.GLIMPSE)
        assert closed.opener_labels == ["Mark"]

    def test_closed_distinction_opener_labels_empty_when_the_opener_was_not_picked(self):
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)
        draft = self._draft()  # Mark never chosen
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        (closed,) = closed_for(draft, OfferChapter.GLIMPSE)
        assert closed.opener_labels == []

    def test_closed_distinction_opener_labels_name_the_section_on_appearance(self):
        """Appearance lines carry a section opener now (#3709), so the closed hint can
        print under the section that would have shown the line."""
        blood = DistinctionFactory(name="Giant's Blood", cost_per_rank=20)
        DistinctionOfferFactory(
            distinction=blood,
            chapter=OfferChapter.APPEARANCE,
            appearance_section=AppearanceSectionFactory(name="Frame"),
        )
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(blood)
        draft = self._draft()
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        (closed,) = closed_for(draft, OfferChapter.APPEARANCE)
        assert closed.opener_labels == ["Frame"]

    def test_closed_distinction_opener_labels_empty_when_no_offer_in_this_chapter_opens_it(self):
        route = OriginTemplateFactory(beginning=self.beginning, closed_reason="Not here.")
        route.closed_distinctions.add(self.scar)  # scar's only offer is chapter=GLIMPSE
        draft = self._draft(glimpse_tag_ids=[self.mark.id])
        draft.selected_origin_template = route
        draft.save(update_fields=["selected_origin_template"])
        (closed,) = closed_for(draft, OfferChapter.APPEARANCE)
        assert closed.opener_labels == []

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

    def test_mutual_exclusion_query_count_stays_flat_as_offers_grow(self):
        """B2 (#3675 final fix): exclusions are fetched in one flat query, not
        one ``mutually_exclusive_with.all()`` per visible offer."""
        draft = self._draft()
        first = DistinctionFactory(name="First", cost_per_rank=1)
        second = DistinctionFactory(name="Second", cost_per_rank=1)
        third = DistinctionFactory(name="Third", cost_per_rank=1)
        first.mutually_exclusive_with.add(second)
        DistinctionOfferFactory(distinction=first, chapter=OfferChapter.APPEARANCE)
        DistinctionOfferFactory(distinction=second, chapter=OfferChapter.APPEARANCE)
        DistinctionOfferFactory(distinction=third, chapter=OfferChapter.APPEARANCE)

        with CaptureQueriesContext(connection) as three_offers:
            offers_for(draft, OfferChapter.APPEARANCE)

        fourth = DistinctionFactory(name="Fourth", cost_per_rank=1)
        DistinctionOfferFactory(distinction=fourth, chapter=OfferChapter.APPEARANCE)

        with self.assertNumQueries(len(three_offers.captured_queries)):
            offers_for(draft, OfferChapter.APPEARANCE)


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
