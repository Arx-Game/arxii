"""ProfileBeginnings: every origin a character holds, with its why (#3775)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_creation.factories import BeginningsFactory
from world.character_sheets.factories import CharacterSheetFactory, ProfileBeginningsFactory
from world.character_sheets.models import ProfileBeginnings
from world.character_sheets.types import ProfileBeginningsSource


class ProfileBeginningsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.profile = cls.sheet.true_profile
        cls.first = BeginningsFactory(name="Peerage")
        cls.second = BeginningsFactory(name="Twilight Court")

    def test_sheet_reads_the_true_profile_set(self):
        ProfileBeginningsFactory(profile=self.profile, beginnings=self.first)
        ProfileBeginningsFactory(
            profile=self.profile,
            beginnings=self.second,
            source=ProfileBeginningsSource.RECOVERED_MEMORY,
            note="Woke under the Catacombs",
        )

        self.assertEqual(set(self.sheet.beginnings), {self.first, self.second})
        row = ProfileBeginnings.objects.get(profile=self.profile, beginnings=self.second)
        self.assertEqual(row.source, ProfileBeginningsSource.RECOVERED_MEMORY)
        self.assertIsNotNone(row.gained_at)

    def test_sheet_without_true_profile_has_no_beginnings(self):
        sheet = CharacterSheetFactory()
        sheet.true_profile = None
        self.assertEqual(list(sheet.beginnings), [])

    def test_one_where_play_began_per_profile(self):
        ProfileBeginningsFactory(profile=self.profile, beginnings=self.first)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProfileBeginningsFactory(profile=self.profile, beginnings=self.second)

    def test_same_beginnings_twice_is_refused(self):
        ProfileBeginningsFactory(profile=self.profile, beginnings=self.first)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProfileBeginningsFactory(
                profile=self.profile,
                beginnings=self.first,
                source=ProfileBeginningsSource.PAST_LIFE,
            )
