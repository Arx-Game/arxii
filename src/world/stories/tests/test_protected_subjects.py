"""Tests for the StoryProtectedSubject model (#2001, replaces StoryNPCDependency #1874)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import BeatFactory, StoryFactory
from world.stories.models import StoryProtectedSubject


class StoryProtectedSubjectModelTests(TestCase):
    def test_story_level_subject_defaults(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=sheet,
        )
        self.assertTrue(subj.is_active)
        self.assertIsNone(subj.beat)
        self.assertEqual(subj.notes, "")
        self.assertIsNotNone(subj.created_at)

    def test_beat_level_subject(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        beat = BeatFactory(episode__chapter__story=story)
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=sheet,
            beat=beat,
        )
        self.assertEqual(subj.beat, beat)

    def test_same_npc_different_stories_allowed(self):
        # Unlike the old StoryNPCDependency, there is no unique_together —
        # a subject may be protected by more than one story simultaneously.
        sheet = CharacterSheetFactory()
        story_a = StoryFactory()
        story_b = StoryFactory()
        subj_a = StoryProtectedSubject.objects.create(
            story=story_a, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=sheet
        )
        subj_b = StoryProtectedSubject.objects.create(
            story=story_b, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=sheet
        )
        self.assertNotEqual(subj_a.pk, subj_b.pk)

    def test_item_subject(self):
        item = ItemInstanceFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.ITEM,
            subject_item=item,
        )
        subj.full_clean()
        self.assertEqual(subj.subject_item, item)

    def test_faction_subject_society(self):
        society = SocietyFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.FACTION,
            subject_society=society,
        )
        subj.full_clean()
        self.assertEqual(subj.subject_society, society)

    def test_faction_subject_organization(self):
        org = OrganizationFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.FACTION,
            subject_organization=org,
        )
        subj.full_clean()
        self.assertEqual(subj.subject_organization, org)

    def test_custom_subject_via_label(self):
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="The Sunken Archive",
        )
        subj.full_clean()
        self.assertEqual(subj.subject_label, "The Sunken Archive")

    def test_clean_rejects_no_subject_populated(self):
        story = StoryFactory()
        subj = StoryProtectedSubject(story=story, subject_kind=StakeSubjectKind.CUSTOM)
        with self.assertRaises(ValidationError):
            subj.full_clean()

    def test_clean_rejects_two_subjects_populated(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject(
            story=story,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=sheet,
            subject_label="Also this",
        )
        with self.assertRaises(ValidationError):
            subj.full_clean()

    def test_str(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory()
        subj = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=sheet,
        )
        self.assertIn("StoryProtectedSubject", str(subj))
        self.assertIn("story-level", str(subj))
