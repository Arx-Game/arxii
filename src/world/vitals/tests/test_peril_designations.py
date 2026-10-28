"""Acute-peril conditions are found by designation, never by name (#4739)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.aftermath import has_acute_peril
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import acute_peril_hand_off_condition_ids
from world.vitals.peril_designations import (
    bleed_out_condition_id,
    designate_unset_peril_conditions,
    plummeting_condition_id,
    surrounded_condition_id,
)
from world.vitals.peril_resolution import acute_peril_condition_ids
from world.vitals.services import get_vitals_consequence_config


class PerilDesignationTests(TestCase):
    def test_unset_designations_find_nothing(self) -> None:
        self.assertIsNone(bleed_out_condition_id())
        self.assertIsNone(plummeting_condition_id())
        self.assertIsNone(surrounded_condition_id())
        self.assertEqual(acute_peril_condition_ids(), [])
        self.assertEqual(acute_peril_hand_off_condition_ids(), [])

    def test_unset_designation_never_matches_a_held_condition(self) -> None:
        """An unset designation must not become ``condition_id IS NULL`` and match."""
        sheet = CharacterSheetFactory()
        ConditionInstanceFactory(target=sheet.character, condition=ConditionTemplateFactory())
        self.assertFalse(has_acute_peril(sheet))

    def test_factory_designates_and_a_rename_changes_nothing(self) -> None:
        bleed = BleedingOutConditionFactory()
        bleed.name = "Lifeblood Ebbing"
        bleed.save(update_fields=["name"])
        sheet = CharacterSheetFactory()
        ConditionInstanceFactory(target=sheet.character, condition=bleed)
        self.assertEqual(bleed_out_condition_id(), bleed.pk)
        self.assertEqual(acute_peril_condition_ids(), [bleed.pk])
        self.assertTrue(has_acute_peril(sheet))

    def test_seed_designation_never_overwrites_staff_choice(self) -> None:
        chosen = ConditionTemplateFactory(name="Freefall")
        designate_unset_peril_conditions(plummeting=chosen)
        designate_unset_peril_conditions(plummeting=ConditionTemplateFactory(name="Plummeting"))
        self.assertEqual(plummeting_condition_id(), chosen.pk)
        self.assertEqual(get_vitals_consequence_config().plummeting_condition, chosen)
