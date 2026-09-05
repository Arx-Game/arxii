"""Approval turns Upbringing picks into family rows, answers and prose (#3617)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.constants import FamilyPath
from world.character_creation.factories import (
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import CharacterOriginSlot
from world.character_creation.services import finalize_character, set_family_path
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
        draft = self._create_base_draft(new_family_name="Cisternwrights")
        draft.selected_origin_template = template
        draft.draft_data["origin_slots"] = {str(slot.id): "We kept the cisterns."}
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        family = Family.objects.get(name="Cisternwrights")
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

        ``_build_character_full_name`` composes ``f"{first_name} {family_name}"``;
        the NAMED-path family must therefore exist before that call, not just by
        the time ``_apply_sheet_demographics`` runs afterward.
        """
        template = OriginTemplateFactory(beginning=self.beginnings)
        draft = self._create_base_draft(first_name="Cara", new_family_name="Cisternwrights")
        draft.selected_origin_template = template
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert character.db_key == "Cara Cisternwrights"
        assert sheet.family.name == "Cisternwrights"


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


class PathSwitchFinalizeTest(FinalizationTestMixin, TestCase):
    """A path switch after a claim invalidates that claim, all the way to finalize (#3617)."""

    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="path_switch_finalize")
        self._setup_finalization_base(self, prefix="Path Switch", height_min=700, height_max=800)

    def test_switching_from_claimed_to_named_finalizes_with_the_new_family(self) -> None:
        """The stale claimed family is dropped; the character gets the NEW named one."""
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        template = OriginTemplateFactory(
            beginning=self.beginnings, allows_claim_family=True, allows_name_family=True
        )
        claimed_family = FamilyFactory(kind=crime, origin_realm=self.area.realm)
        draft = self._create_base_draft()
        draft.selected_origin_template = template
        draft.family_path = FamilyPath.CLAIMED
        draft.family = claimed_family
        draft.save()

        set_family_path(draft, FamilyPath.NAMED)
        draft.draft_data["new_family_name"] = "Newcomers"
        draft.save(update_fields=["draft_data"])

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        new_family = Family.objects.get(name="Newcomers")
        assert sheet.family == new_family
        assert sheet.family != claimed_family

    def test_switching_to_none_path_finalizes_with_no_family(self) -> None:
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        template = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_name_family=False,
            allows_claim_family=True,
            allows_no_family=True,
        )
        claimed_family = FamilyFactory(kind=crime, origin_realm=self.area.realm)
        draft = self._create_base_draft()
        draft.selected_origin_template = template
        draft.family_path = FamilyPath.CLAIMED
        draft.family = claimed_family
        draft.save()

        set_family_path(draft, FamilyPath.NONE)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert sheet.family is None

    def test_hidden_slot_choice_is_not_persisted_after_path_switch(self) -> None:
        """A costed claim-only choice picked before switching to NAMED is dropped, not stored."""
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        template = OriginTemplateFactory(
            beginning=self.beginnings, allows_claim_family=True, allows_name_family=True
        )
        slot = OriginTemplateSlotFactory(
            template=template, name="Role", allows_text=False, applies_to=FamilyPath.CLAIMED
        )
        choice = OriginTemplateSlotChoiceFactory(slot=slot, cost_per_influence=3)
        claimed_family = FamilyFactory(kind=crime, influence=2, origin_realm=self.area.realm)
        draft = self._create_base_draft()
        draft.selected_origin_template = template
        draft.family_path = FamilyPath.CLAIMED
        draft.family = claimed_family
        draft.draft_data["origin_choices"] = {str(slot.id): choice.id}
        draft.save()
        assert draft.calculate_upbringing_cost() == template.cg_point_cost + 6

        set_family_path(draft, FamilyPath.NAMED)
        draft.draft_data["new_family_name"] = "Vale"
        draft.save(update_fields=["draft_data"])
        assert draft.calculate_upbringing_cost() == template.cg_point_cost

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert not CharacterOriginSlot.objects.filter(sheet=sheet, slot=slot).exists()
