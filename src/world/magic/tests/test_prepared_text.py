"""Prepared per-character text layers above patron and tier (#4101 Task 4)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.magic.factories import (
    AudereMajoraCrossingFactory,
    AudereMajoraFaithVariantFactory,
    AudereMajoraThresholdFactory,
    AudereThresholdFactory,
    CharacterCrossingTextFactory,
    CharacterSurgeTextFactory,
)
from world.magic.services.prepared_text import (
    consume_prepared_crossing_text,
    may_prepare_text_for,
    resolve_crossing_text,
    resolve_surge_text,
    unused_prepared_crossing_text,
)


class CrossingTextLayeringTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.threshold = AudereMajoraThresholdFactory(
            vision_text="tier vision", manifestation_text="tier room", deed_title="Tier Deed"
        )
        cls.variant = AudereMajoraFaithVariantFactory(
            threshold=cls.threshold, vision_text="patron vision", manifestation_text="patron room"
        )

    def test_tier_when_nothing_else(self):
        text = resolve_crossing_text(self.sheet, self.threshold, None)
        self.assertEqual(
            (text.vision, text.manifestation, text.deed_title, text.prepared),
            ("tier vision", "tier room", "Tier Deed", False),
        )

    def test_patron_over_tier(self):
        text = resolve_crossing_text(self.sheet, self.threshold, self.variant)
        self.assertEqual((text.vision, text.manifestation), ("patron vision", "patron room"))

    def test_character_over_patron_field_by_field(self):
        sheet = CharacterSheetFactory()
        CharacterCrossingTextFactory(
            character_sheet=sheet, vision_text="her vision", manifestation_text=""
        )
        text = resolve_crossing_text(sheet, self.threshold, self.variant)
        self.assertEqual(text.vision, "her vision")
        self.assertEqual(text.manifestation, "patron room")  # blank falls through
        self.assertTrue(text.prepared)

    # Demo-fidelity fix round (#4101, F8): __str__ names the character instead
    # of printing the sheet pk / crossing pk pair.
    def test_crossing_text_str_names_the_character(self):
        sheet = CharacterSheetFactory()
        text = CharacterCrossingTextFactory(character_sheet=sheet)
        self.assertEqual(str(text), f"Crossing text for {sheet.character.key}")

    def test_surge_text_str_names_the_character(self):
        sheet = CharacterSheetFactory()
        text = CharacterSurgeTextFactory(character_sheet=sheet)
        self.assertEqual(str(text), f"Surge text for {sheet.character.key}")

    def test_consumed_text_no_longer_applies(self):
        sheet = CharacterSheetFactory()
        CharacterCrossingTextFactory(character_sheet=sheet, vision_text="once")
        crossing = AudereMajoraCrossingFactory(character_sheet=sheet, threshold=self.threshold)
        consume_prepared_crossing_text(sheet, crossing)
        self.assertIsNone(unused_prepared_crossing_text(sheet))
        self.assertEqual(resolve_crossing_text(sheet, self.threshold, None).vision, "tier vision")


class SurgeTextLayeringTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.threshold = AudereThresholdFactory(surge_manifestation_text="tier surge")

    def test_character_over_tier(self):
        sheet = CharacterSheetFactory()
        CharacterSurgeTextFactory(character_sheet=sheet, surge_text="her surge")
        self.assertEqual(resolve_surge_text(sheet, self.threshold).text, "her surge")

    def test_tier_for_sheetless(self):
        self.assertEqual(resolve_surge_text(None, self.threshold).text, "tier surge")


class MayPrepareTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.table_gm = GMProfileFactory()
        table = GMTableFactory(gm=cls.table_gm)
        GMTableMembershipFactory(table=table, persona=cls.sheet.primary_persona)
        cls.stranger_gm = GMProfileFactory()
        cls.staff = AccountFactory(is_staff=True)

    def test_table_gm_may(self):
        self.assertTrue(may_prepare_text_for(self.table_gm.account, self.sheet))

    def test_other_gm_may_not(self):
        self.assertFalse(may_prepare_text_for(self.stranger_gm.account, self.sheet))

    def test_staff_may(self):
        self.assertTrue(may_prepare_text_for(self.staff, self.sheet))
