"""Group/person/branched answer validation and bundled-Distinction conflicts (#3660)."""

from django.test import TestCase

from world.character_creation.constants import (
    AnchorSource,
    QuestionKind,
)
from world.character_creation.factories import (
    CharacterDraftFactory,
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.validators import get_lineage_errors
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory


def _draft(template, **data):
    return CharacterDraftFactory(
        selected_area=template.beginning.starting_area,
        selected_beginnings=template.beginning,
        selected_origin_template=template,
        draft_data={"tarot_card_name": "The Lamp", **data},
    )


class ConnectionValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        cls.house = OrganizationFactory(name="House Orisant")
        cls.other = OrganizationFactory(name="Not offered")
        cls.q1 = GroupPromptFactory(template=cls.template, sort_order=0, name="House")
        cls.q1.anchor_orgs.add(cls.house)
        cls.livery = OriginTemplateSlotChoiceFactory(slot=cls.q1, name="Livery")
        cls.person = OriginTemplateSlotFactory(
            template=cls.template,
            sort_order=1,
            name="Who",
            kind=QuestionKind.PERSON,
            same_anchor_as=cls.q1,
            follow_up_to=cls.q1,
        )

    def test_required_group_question_needs_anchor_and_stance(self):
        errors = get_lineage_errors(_draft(self.template))
        assert "House is required" in errors

    def test_anchor_outside_the_offered_groups_is_rejected(self):
        draft = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.other.id},
            origin_choices={str(self.q1.id): self.livery.id},
        )
        assert "That group is not offered for House" in get_lineage_errors(draft)

    def test_answer_from_another_question_is_rejected(self):
        other_slot = OriginTemplateSlotFactory(
            template=self.template, sort_order=2, name="Elsewhere", kind=QuestionKind.PICK
        )
        stray = OriginTemplateSlotChoiceFactory(slot=other_slot, name="Keys")
        draft = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.house.id},
            origin_choices={str(self.q1.id): stray.id},
        )
        assert "Invalid choice for House" in get_lineage_errors(draft)

    def test_person_required_only_when_shown(self):
        self.person.is_required = True
        self.person.save()
        unshown = _draft(self.template)
        assert "Who is required" not in get_lineage_errors(unshown)
        shown = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.house.id},
            origin_choices={str(self.q1.id): self.livery.id},
        )
        assert "Who is required" in get_lineage_errors(shown)
        answered = _draft(
            self.template,
            origin_anchors={str(self.q1.id): self.house.id},
            origin_choices={str(self.q1.id): self.livery.id},
            origin_figures={str(self.person.id): "Tessaline"},
        )
        assert get_lineage_errors(answered) == []


class OwnFamilyGroupLineageTest(TestCase):
    """A GROUP question sourced OWN_FAMILY needs no origin_anchors entry (#3660 ruling A)."""

    def test_own_family_group_validates_with_no_origin_anchors_entry(self):
        family = FamilyFactory(influence=2, is_playable=True)
        OrganizationFactory(name="Hold", family=family)
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=False)
        slot = GroupPromptFactory(template=template, anchor_source=AnchorSource.OWN_FAMILY)
        choice = OriginTemplateSlotChoiceFactory(slot=slot, name="Stayed close")
        draft = _draft(template, origin_choices={str(slot.id): choice.id})
        draft.family = family
        draft.family_path = "claimed"
        assert get_lineage_errors(draft) == []
