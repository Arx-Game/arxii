"""Schema and clean() rules for connection prompts (#3660)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_creation.constants import (
    AnchorSource,
    ConnectionKind,
    LifeStage,
    QuestionKind,
)
from world.character_creation.factories import (
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory, SocietyFactory


class ConnectionSlotSchemaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        cls.gang = OrganizationTypeFactory(name="gang")
        cls.luxen = SocietyFactory(name="Luxen")

    def test_defaults_keep_existing_rows_as_free_text(self):
        slot = OriginTemplateSlotFactory(template=self.template)
        assert slot.kind == QuestionKind.TEXT
        assert slot.connection_kind == ""
        assert slot.life_stage == ""
        assert slot.anchor_source == ""
        assert slot.is_connection is False

    def test_group_question_with_pool_is_valid(self):
        slot = OriginTemplateSlotFactory(
            template=self.template,
            kind=QuestionKind.GROUP,
            connection_kind=ConnectionKind.RAISED_BY,
            life_stage=LifeStage.CHILDHOOD,
            anchor_source=AnchorSource.POOL,
            anchor_org_type=self.gang,
            anchor_society=self.luxen,
        )
        slot.full_clean()
        assert slot.is_connection is True

    def test_group_question_without_a_source_is_rejected(self):
        slot = OriginTemplateSlotFactory.build(template=self.template, kind=QuestionKind.GROUP)
        with self.assertRaises(ValidationError):
            slot.full_clean()

    def test_pool_source_needs_type_or_society(self):
        slot = OriginTemplateSlotFactory.build(
            template=self.template, kind=QuestionKind.GROUP, anchor_source=AnchorSource.POOL
        )
        with self.assertRaises(ValidationError):
            slot.full_clean()

    def test_same_as_must_point_at_an_earlier_group_question(self):
        first = OriginTemplateSlotFactory(
            template=self.template,
            sort_order=0,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.LISTED,
        )
        first.anchor_orgs.add(OrganizationFactory(org_type=self.gang))
        later = OriginTemplateSlotFactory.build(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.SAME_AS,
            same_anchor_as=first,
        )
        later.full_clean()  # earlier + group: fine
        backwards = OriginTemplateSlotFactory.build(
            template=self.template,
            sort_order=0,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.SAME_AS,
            same_anchor_as=OriginTemplateSlotFactory(
                template=self.template,
                sort_order=5,
                kind=QuestionKind.GROUP,
                anchor_source=AnchorSource.LISTED,
            ),
        )
        with self.assertRaises(ValidationError):
            backwards.full_clean()

    def test_branch_choices_must_belong_to_the_follow_up_target(self):
        first = OriginTemplateSlotFactory(
            template=self.template, sort_order=0, kind=QuestionKind.PICK, allows_text=False
        )
        other = OriginTemplateSlotFactory(
            template=self.template, sort_order=1, kind=QuestionKind.PICK, allows_text=False
        )
        foreign_choice = OriginTemplateSlotChoiceFactory(slot=other)
        branched = OriginTemplateSlotFactory(
            template=self.template, sort_order=2, follow_up_to=first
        )
        branched.shown_for_choices.add(foreign_choice)
        with self.assertRaises(ValidationError):
            branched.full_clean()

    def test_person_question_belongs_to_a_group_question(self):
        group = OriginTemplateSlotFactory(
            template=self.template,
            sort_order=0,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.LISTED,
        )
        person = OriginTemplateSlotFactory.build(
            template=self.template, sort_order=1, kind=QuestionKind.PERSON, same_anchor_as=group
        )
        person.full_clean()
        person_no_group = OriginTemplateSlotFactory.build(
            template=self.template, sort_order=1, kind=QuestionKind.PERSON
        )
        person_no_group.full_clean()  # a person with no group is allowed


class ConnectionChoiceSchemaTest(TestCase):
    def test_choice_carries_seed_and_trust(self):
        slot = OriginTemplateSlotFactory(kind=QuestionKind.GROUP, anchor_source=AnchorSource.LISTED)
        choice = OriginTemplateSlotChoiceFactory(
            slot=slot,
            reputation_seed=300,
            trust_required=0,
        )
        choice.full_clean()
        assert choice.reputation_seed == 300

    def test_seed_only_on_a_group_question(self):
        slot = OriginTemplateSlotFactory(kind=QuestionKind.PICK, allows_text=False)
        choice = OriginTemplateSlotChoiceFactory.build(slot=slot, reputation_seed=100)
        with self.assertRaises(ValidationError):
            choice.full_clean()

    def test_answer_on_a_text_question_is_rejected(self):
        """Carry-over from Task 3's review, Builder review Finding 3 (#3660)."""
        slot = OriginTemplateSlotFactory(kind=QuestionKind.TEXT)
        choice = OriginTemplateSlotChoiceFactory.build(slot=slot)
        with self.assertRaises(ValidationError):
            choice.full_clean()

    def test_answer_on_a_person_question_is_rejected(self):
        slot = OriginTemplateSlotFactory(kind=QuestionKind.PERSON)
        choice = OriginTemplateSlotChoiceFactory.build(slot=slot)
        with self.assertRaises(ValidationError):
            choice.full_clean()

    def test_answer_on_a_pick_question_is_allowed(self):
        slot = OriginTemplateSlotFactory(kind=QuestionKind.PICK, allows_text=False)
        choice = OriginTemplateSlotChoiceFactory.build(slot=slot)
        choice.full_clean()
