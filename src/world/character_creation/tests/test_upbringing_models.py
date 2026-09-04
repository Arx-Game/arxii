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
from world.character_creation.models import Beginnings, OriginTemplate


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
