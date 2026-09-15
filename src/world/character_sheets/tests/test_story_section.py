"""Tests for the sheet payload's story section (#3660).

Covers the entity-linked/life-stage-tagged origin-slot fields
(``kind``, ``connection_kind``, ``life_stage``, ``choice_name``,
``choice_description``, ``organization_id``, ``organization_name``,
``figure_name``) and the foreign-viewer redaction of ``figure_name``.
"""

from django.test import TestCase

from world.character_creation.constants import ConnectionKind, LifeStage, QuestionKind
from world.character_creation.factories import (
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.services import set_origin_slot
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.serializers import _build_story
from world.societies.factories import OrganizationFactory


class StorySectionOriginSlotsTest(TestCase):
    """``_build_story`` surfaces the tie/figure fields and gates ``figure_name`` (#3660)."""

    def test_story_origin_slots_carry_tie_fields_and_hide_person_for_strangers(self) -> None:
        sheet = CharacterSheetFactory()

        group_slot = OriginTemplateSlotFactory(
            kind=QuestionKind.GROUP,
            connection_kind=ConnectionKind.RAISED_BY,
            life_stage=LifeStage.CHILDHOOD,
        )
        org = OrganizationFactory(name="House Orisant")
        choice = OriginTemplateSlotChoiceFactory(slot=group_slot, name="Livery at table")
        set_origin_slot(sheet, group_slot, "", choice=choice, organization=org)

        person_slot = OriginTemplateSlotFactory(
            template=group_slot.template,
            kind=QuestionKind.PERSON,
            connection_kind=ConnectionKind.RAISED_BY,
            life_stage=LifeStage.CHILDHOOD,
            sort_order=group_slot.sort_order + 1,
        )
        set_origin_slot(sheet, person_slot, "", figure_name="Tessaline")

        section = _build_story(sheet=sheet, bio_profile=sheet.true_profile, privileged=False)
        group_row = next(r for r in section["origin_slots"] if r["kind"] == "group")
        assert group_row["organization_name"] == "House Orisant"
        assert group_row["organization_id"] == org.pk
        assert group_row["choice_name"] == "Livery at table"
        person_row = next(r for r in section["origin_slots"] if r["kind"] == "person")
        assert person_row["figure_name"] == ""

        own = _build_story(sheet=sheet, bio_profile=sheet.true_profile, privileged=True)
        assert (
            next(r for r in own["origin_slots"] if r["kind"] == "person")["figure_name"]
            == "Tessaline"
        )

    def test_story_origin_slot_without_choice_or_organization_is_blank(self) -> None:
        sheet = CharacterSheetFactory()
        slot = OriginTemplateSlotFactory(kind=QuestionKind.TEXT)
        set_origin_slot(sheet, slot, "Just a write-in answer.")

        section = _build_story(sheet=sheet, bio_profile=sheet.true_profile, privileged=True)
        row = next(r for r in section["origin_slots"] if r["slot_id"] == slot.pk)
        assert row["choice_name"] == ""
        assert row["choice_description"] == ""
        assert row["organization_id"] is None
        assert row["organization_name"] == ""
        assert row["figure_name"] == ""
        assert row["connection_kind"] == ""
        assert row["life_stage"] == ""
