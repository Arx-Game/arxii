"""Visibility, group resolution, pricing and bundled Distinctions (#3660)."""

from django.test import TestCase

from world.character_creation.constants import AnchorSource, QuestionKind
from world.character_creation.factories import (
    CharacterDraftFactory,
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.questionnaire import (
    DraftAnswers,
    anchor_for,
    bundled_distinctions,
    is_answered,
    resolve_groups,
    visible_slot_ids,
)
from world.distinctions.factories import DistinctionFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory, SocietyFactory


def _draft(template, **data):
    return CharacterDraftFactory(
        selected_area=template.beginning.starting_area,
        selected_beginnings=template.beginning,
        selected_origin_template=template,
        draft_data=data,
    )


class VisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        cls.house = OrganizationFactory(name="House Orisant")
        cls.q1 = GroupPromptFactory(template=cls.template, sort_order=0, name="House")
        cls.q1.anchor_orgs.add(cls.house)
        cls.scullery = OriginTemplateSlotChoiceFactory(slot=cls.q1, name="Scullery")
        cls.livery = OriginTemplateSlotChoiceFactory(slot=cls.q1, name="Livery at table")
        cls.q2 = OriginTemplateSlotFactory(
            template=cls.template,
            sort_order=1,
            name="Person",
            kind=QuestionKind.PERSON,
            same_anchor_as=cls.q1,
            follow_up_to=cls.q1,
            is_required=False,
        )
        cls.q3 = GroupPromptFactory(
            template=cls.template,
            sort_order=2,
            name="Crime family",
            follow_up_to=cls.q1,
            is_required=False,
        )
        cls.q3.shown_for_choices.add(cls.livery)
        cls.q3.anchor_orgs.add(OrganizationFactory(name="the Rouault"))

    def test_follow_ups_hidden_until_target_answered(self):
        draft = _draft(self.template, origin_anchors={}, origin_choices={})
        assert visible_slot_ids(draft) == {self.q1.id}

    def test_follow_up_shown_whatever_the_answer_when_no_branch_choices(self):
        draft = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.house.id},
            origin_choices={str(self.q1.id): self.scullery.id},
        )
        assert self.q2.id in visible_slot_ids(draft)
        assert self.q3.id not in visible_slot_ids(draft)  # scullery is not a branch answer

    def test_branch_shown_for_ticked_answer(self):
        draft = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.house.id},
            origin_choices={str(self.q1.id): self.livery.id},
        )
        assert visible_slot_ids(draft) == {self.q1.id, self.q2.id, self.q3.id}


class ResolveGroupsTest(TestCase):
    def test_pool_filters_type_society_and_covert(self):
        gang = OrganizationTypeFactory(name="gang")
        covert = OrganizationTypeFactory(name="cabal", is_covert=True)
        luxen = SocietyFactory(name="Luxen")
        a = OrganizationFactory(name="A", org_type=gang, society=luxen)
        OrganizationFactory(name="B", org_type=gang, society=SocietyFactory(name="Umbros"))
        OrganizationFactory(name="C", org_type=covert, society=luxen)
        slot = GroupPromptFactory(
            anchor_source=AnchorSource.POOL, anchor_org_type=gang, anchor_society=luxen
        )
        draft = _draft(slot.template)
        assert resolve_groups(slot, draft, DraftAnswers.from_draft(draft)) == [a]

    def test_same_as_reuses_the_earlier_answer(self):
        template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        q1 = GroupPromptFactory(template=template, sort_order=0)
        org = OrganizationFactory(name="House Orisant")
        q1.anchor_orgs.add(org)
        q2 = GroupPromptFactory(
            template=template,
            sort_order=1,
            anchor_source=AnchorSource.SAME_AS,
            same_anchor_as=q1,
            follow_up_to=q1,
        )
        draft = _draft(template, origin_anchors={str(q1.id): org.id})
        assert resolve_groups(q2, draft, DraftAnswers.from_draft(draft)) == [org]

    def test_own_family_is_the_family_org(self):
        family = FamilyFactory(influence=3)
        org = OrganizationFactory(name="Hold", family=family)
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=False)
        slot = GroupPromptFactory(template=template, anchor_source=AnchorSource.OWN_FAMILY)
        draft = _draft(template)
        draft.family = family
        draft.family_path = "claimed"
        assert resolve_groups(slot, draft, DraftAnswers.from_draft(draft)) == [org]


class PricingAndBundleTest(TestCase):
    def test_group_answer_prices_off_the_groups_family_and_bundles_the_grant(self):
        family = FamilyFactory(influence=5)
        crew = OrganizationFactory(name="the Rouault", family=family)
        template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        slot = GroupPromptFactory(template=template)
        slot.anchor_orgs.add(crew)
        kept_close = DistinctionFactory(name="Kept Close", cost_per_rank=15)
        courier = OriginTemplateSlotChoiceFactory(
            slot=slot,
            name="Courier",
            cg_point_cost=10,
            cost_per_influence=1,
            grants_distinction=kept_close,
            reputation_seed=200,
        )
        draft = _draft(
            template,
            origin_anchors={str(slot.id): crew.id},
            origin_choices={str(slot.id): courier.id},
        )
        assert draft.calculate_upbringing_cost() == 10 + 1 * 5
        bundled = bundled_distinctions(draft)
        assert [b["distinction_id"] for b in bundled] == [kept_close.id]
        assert bundled[0]["organization_name"] == "the Rouault"

    def test_hidden_answers_do_not_price(self):
        template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        q1 = GroupPromptFactory(template=template, sort_order=0)
        org = OrganizationFactory(name="House")
        q1.anchor_orgs.add(org)
        q2 = GroupPromptFactory(
            template=template,
            sort_order=1,
            follow_up_to=q1,
            anchor_source=AnchorSource.SAME_AS,
            same_anchor_as=q1,
        )
        dear = OriginTemplateSlotChoiceFactory(slot=q2, cg_point_cost=25)
        draft = _draft(template, origin_anchors={}, origin_choices={str(q2.id): dear.id})
        assert draft.calculate_upbringing_cost() == 0


class OwnFamilyAnchorTest(TestCase):
    """Ruling A: a GROUP question sourced from the family needs no origin_anchors entry."""

    def test_own_family_group_is_answered_without_an_origin_anchors_entry(self):
        family = FamilyFactory(influence=2)
        org = OrganizationFactory(name="Hold", family=family)
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=False)
        slot = GroupPromptFactory(template=template, anchor_source=AnchorSource.OWN_FAMILY)
        choice = OriginTemplateSlotChoiceFactory(slot=slot, name="Stayed close")
        draft = _draft(template, origin_choices={str(slot.id): choice.id})
        draft.family = family
        draft.family_path = "claimed"
        answers = DraftAnswers.from_draft(draft)
        choice_ids_by_slot = {slot.id: {choice.id}}

        assert is_answered(slot, draft, answers, choice_ids_by_slot) is True
        assert anchor_for(slot, draft, answers) == org.id


class AnchorlessGroupPricingTest(TestCase):
    """Ruling B: OWN_FAMILY/SERVED_HOUSE GROUP answers price off the resolved org."""

    def test_own_family_group_prices_off_the_familys_influence(self):
        family = FamilyFactory(influence=3)
        OrganizationFactory(name="Hold", family=family)
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=False)
        slot = GroupPromptFactory(template=template, anchor_source=AnchorSource.OWN_FAMILY)
        choice = OriginTemplateSlotChoiceFactory(
            slot=slot, name="Stayed close", cg_point_cost=2, cost_per_influence=1
        )
        draft = _draft(template, origin_choices={str(slot.id): choice.id})
        draft.family = family
        draft.family_path = "claimed"

        assert draft.calculate_upbringing_cost() == 2 + 3

    def test_served_house_group_prices_off_the_house_familys_influence(self):
        house_family = FamilyFactory(influence=4)
        house = OrganizationFactory(name="House Ostrean", family=house_family)
        template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        slot = GroupPromptFactory(template=template, anchor_source=AnchorSource.SERVED_HOUSE)
        choice = OriginTemplateSlotChoiceFactory(
            slot=slot, name="Loyal retainer", cg_point_cost=2, cost_per_influence=1
        )
        draft = _draft(template, origin_choices={str(slot.id): choice.id})
        draft.served_house = house

        assert draft.calculate_upbringing_cost() == 2 + 4
