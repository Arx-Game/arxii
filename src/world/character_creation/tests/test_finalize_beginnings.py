"""Finalize records the chosen Beginnings as where play began (#3775)."""

from django.test import TestCase

from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.character_creation.services import _set_beginnings
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import ProfileBeginnings
from world.character_sheets.types import ProfileBeginningsSource


class SetBeginningsTests(TestCase):
    def test_writes_one_character_creation_row(self):
        beginnings = BeginningsFactory(name="Peerage")
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        sheet = CharacterSheetFactory()

        _set_beginnings(sheet, draft)

        row = ProfileBeginnings.objects.get(profile=sheet.true_profile)
        self.assertEqual(row.beginnings, beginnings)
        self.assertEqual(row.source, ProfileBeginningsSource.CHARACTER_CREATION)

    def test_idempotent(self):
        beginnings = BeginningsFactory(name="Peerage")
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        sheet = CharacterSheetFactory()

        _set_beginnings(sheet, draft)
        _set_beginnings(sheet, draft)

        self.assertEqual(ProfileBeginnings.objects.filter(profile=sheet.true_profile).count(), 1)

    def test_no_beginnings_writes_nothing(self):
        draft = CharacterDraftFactory(selected_beginnings=None)
        sheet = CharacterSheetFactory()

        _set_beginnings(sheet, draft)

        self.assertFalse(ProfileBeginnings.objects.filter(profile=sheet.true_profile).exists())
