"""Upbringing schema on the origin-template models (#3617)."""

import importlib

from django.apps import apps as django_apps
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
from world.roster.constants import COMMONER_KIND_NAME
from world.roster.factories import FamilyKindFactory


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


class BackfillUpbringingsTest(TestCase):
    """world.migrations.0220_upbringings.apply_family_known"""

    def setUp(self):
        self.module = importlib.import_module("world.migrations.0220_upbringings")
        self.OriginTemplate = django_apps.get_model("arxii", "OriginTemplate")
        self.commoner = FamilyKindFactory(name=COMMONER_KIND_NAME)

    def test_no_templates_and_unknown_family_creates_an_unknown_starter(self):
        beginning = BeginningsFactory()
        self.module.apply_family_known(
            self.OriginTemplate, self.commoner, beginning, family_known=False
        )
        starter = OriginTemplate.objects.get(beginning=beginning)
        assert starter.name == "Unknown"
        assert starter.allows_no_family
        assert not starter.allows_claim_family
        assert not starter.allows_name_family

    def test_no_templates_and_known_family_creates_a_known_family_starter(self):
        beginning = BeginningsFactory()
        self.module.apply_family_known(
            self.OriginTemplate, self.commoner, beginning, family_known=True
        )
        starter = OriginTemplate.objects.get(beginning=beginning)
        assert starter.name == "Known family"
        assert starter.allows_claim_family
        assert starter.allows_name_family
        assert starter.named_family_kind.name == COMMONER_KIND_NAME

    def test_existing_template_is_widened_not_duplicated_when_family_known(self):
        beginning = BeginningsFactory()
        template = OriginTemplateFactory(
            beginning=beginning,
            allows_name_family=False,
            named_family_kind=None,
            allows_no_family=True,
        )
        self.module.apply_family_known(
            self.OriginTemplate, self.commoner, beginning, family_known=True
        )
        template.refresh_from_db()
        assert template.allows_claim_family
        assert template.allows_name_family
        assert template.named_family_kind.name == COMMONER_KIND_NAME
        assert OriginTemplate.objects.filter(beginning=beginning).count() == 1

    def test_existing_template_is_widened_not_duplicated_when_family_unknown(self):
        beginning = BeginningsFactory()
        template = OriginTemplateFactory(beginning=beginning)  # factory default: name path
        self.module.apply_family_known(
            self.OriginTemplate, self.commoner, beginning, family_known=False
        )
        template.refresh_from_db()
        assert template.allows_no_family
        assert OriginTemplate.objects.filter(beginning=beginning).count() == 1
