"""Upbringing schema on the origin-template models (#3617)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_creation.constants import FamilyPath
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
    make_unknown_upbringing,
)
from world.character_creation.models import (
    Beginnings,
    OriginTemplate,
    OriginTemplateSlot,
)


class UpbringingFieldsTest(TestCase):
    def test_at_least_one_family_path_is_enforced(self):
        beginning = BeginningsFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            OriginTemplate.objects.create(
                beginning=beginning,
                name="No paths",
                frame_narrative="x",
                allows_claim_family=False,
                allows_name_family=False,
                allows_no_family=False,
            )

    def test_allowed_family_paths_lists_the_switches_that_are_on(self):
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        assert template.allowed_family_paths() == [FamilyPath.CLAIMED, FamilyPath.NAMED]

    def test_resolve_family_path_auto_picks_a_single_allowed_path(self):
        template = make_unknown_upbringing(BeginningsFactory())
        draft = CharacterDraftFactory(
            selected_beginnings=template.beginning, selected_origin_template=template
        )
        assert draft.resolve_family_path() == FamilyPath.NONE

    def test_resolve_family_path_needs_a_choice_when_several_are_allowed(self):
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        draft = CharacterDraftFactory(
            selected_beginnings=template.beginning, selected_origin_template=template
        )
        assert draft.resolve_family_path() == ""
        draft.family_path = FamilyPath.NAMED
        assert draft.resolve_family_path() == FamilyPath.NAMED
        draft.family_path = FamilyPath.NONE  # not allowed by this template
        assert draft.resolve_family_path() == ""

    def test_choice_rows_hang_off_a_prompt(self):
        slot = OriginTemplateSlotFactory(allows_text=False)
        choice = OriginTemplateSlotChoiceFactory(slot=slot, cg_point_cost=1, cost_per_influence=3)
        assert list(slot.choices.all()) == [choice]

    def test_beginnings_no_longer_has_family_known(self):
        assert not any(f.name == "family_known" for f in Beginnings._meta.get_fields())


class UpbringingQuestionsHandlerTest(TestCase):
    """The handler that owns a route's questions for every consumer (#3673).

    Two hazards, and each needs its own half of the contract. A cache hung off
    an identity-mapped Upbringing outlives the request that filled it, so a
    question added or edited afterwards has to clear it - that is the writer
    side, ``OriginTemplateSlot.related_cache_fields``. And a delete that never
    calls ``Model.delete()`` never reaches that writer side at all, while
    ``Collector.delete()`` still nulls the pk on the shared instance - so the
    handler drops pk-less rows itself before returning anything.
    """

    def setUp(self):
        self.template = OriginTemplateFactory()
        self.first = OriginTemplateSlotFactory(template=self.template, name="First", sort_order=0)

    def test_questions_come_back_in_the_order_a_player_answers_them(self):
        later = OriginTemplateSlotFactory(template=self.template, name="Later", sort_order=5)
        middle = OriginTemplateSlotFactory(template=self.template, name="Middle", sort_order=2)
        assert list(self.template.questions) == [self.first, middle, later]

    def test_a_question_added_after_the_first_read_shows_up(self):
        assert list(self.template.questions) == [self.first]
        added = OriginTemplateSlotFactory(template=self.template, name="Added", sort_order=1)
        assert list(self.template.questions) == [self.first, added], (
            "the handler served a stale list; saving a question must clear its "
            "Upbringing's cached properties via related_cache_fields"
        )

    def test_a_deleted_question_is_gone_from_a_warm_handler(self):
        doomed = OriginTemplateSlotFactory(template=self.template, name="Doomed", sort_order=1)
        assert doomed in list(self.template.questions)
        doomed.delete()
        assert list(self.template.questions) == [self.first]

    def test_a_queryset_delete_is_caught_even_though_it_never_calls_delete(self):
        """The belt. ``queryset.delete()`` bypasses ``Model.delete()``, so no
        writer-side clearing happens - but the collector still nulls the pk on
        the shared instance, and the handler refuses to hand that back."""
        doomed = OriginTemplateSlotFactory(template=self.template, name="Doomed", sort_order=1)
        warm = list(self.template.questions)
        assert doomed in warm

        OriginTemplateSlot.objects.filter(pk=doomed.pk).delete()

        assert doomed.pk is None, "the collector no longer nulls the pk; revisit the handler"
        served = list(self.template.questions)
        assert served == [self.first], (
            f"a question deleted through a queryset is still being served: {served}"
        )
