"""Approval turns Upbringing picks into family rows, answers and prose (#3617)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.factories import (
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import CharacterOriginSlot
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import COMMONER_KIND_NAME, CRIME_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.roster.models import Family


class NamedFamilyFinalizeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="named_family_finalize")
        self._setup_finalization_base(self, prefix="Named Family", height_min=700, height_max=800)

    def test_named_family_is_created_and_bound(self) -> None:
        template = OriginTemplateFactory(beginning=self.beginnings)
        slot = OriginTemplateSlotFactory(template=template, name="Duty")
        draft = self._create_base_draft(new_family_name="The Cisternwrights")
        draft.selected_origin_template = template
        draft.draft_data["origin_slots"] = {str(slot.id): "We kept the cisterns."}
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        family = Family.objects.get(name="The Cisternwrights")
        assert family.kind.name == COMMONER_KIND_NAME
        assert family.created_by_cg is True
        assert family.created_by == self.account
        assert family.influence == 0
        assert family.origin_realm == self.area.realm
        assert sheet.family == family
        assert sheet.kinsperson.family == family
        row = CharacterOriginSlot.objects.get(sheet=sheet, slot=slot)
        assert row.value == "We kept the cisterns."
        assert row.choice is None
        assert "We kept the cisterns." in sheet.background

    def test_named_family_surname_used_in_character_name(self) -> None:
        """The family is created (and its name used) before the character name (#3617).

        ``_build_character_full_name`` composes ``f"{first_name} {family_name}"`` —
        the NAMED-path family must therefore exist before that call, not just by
        the time ``_apply_sheet_demographics`` runs afterward.
        """
        template = OriginTemplateFactory(beginning=self.beginnings)
        draft = self._create_base_draft(first_name="Cara", new_family_name="The Cisternwrights")
        draft.selected_origin_template = template
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert character.db_key == "Cara The Cisternwrights"
        assert sheet.family.name == "The Cisternwrights"


class ClaimedFamilyFinalizeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="claimed_family_finalize")
        self._setup_finalization_base(self, prefix="Claimed Family", height_min=700, height_max=800)

    def test_choice_answer_is_stored_and_rendered(self) -> None:
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        template = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_name_family=False,
            named_family_kind=None,
            allows_claim_family=True,
        )
        slot = OriginTemplateSlotFactory(
            template=template, name="Role", prompt="Your place in it?", allows_text=False
        )
        head = OriginTemplateSlotChoiceFactory(
            slot=slot, name="Head of the family", cost_per_influence=3
        )
        family = FamilyFactory(kind=crime, influence=2, origin_realm=self.area.realm)
        draft = self._create_base_draft()
        draft.selected_origin_template = template
        draft.family = family
        draft.draft_data["origin_choices"] = {str(slot.id): head.id}
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        row = CharacterOriginSlot.objects.get(sheet=sheet, slot=slot)
        assert row.choice == head
        assert "Your place in it?" in sheet.background
        assert "Head of the family" in sheet.background
        assert sheet.family == family


class NoFamilyFinalizeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="no_family_finalize")
        self._setup_finalization_base(self, prefix="No Family", height_min=700, height_max=800)

    def test_none_path_marks_family_unknown(self) -> None:
        draft = self._create_base_draft()
        draft.selected_origin_template = self.unknown_upbringing
        draft.family = None
        draft.draft_data["tarot_card_name"] = self.tarot_card.name
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert sheet.family is None
        assert sheet.tarot_card == self.tarot_card
