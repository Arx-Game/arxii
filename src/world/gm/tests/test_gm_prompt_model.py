"""GMPrompt is the generalized DramaticMomentSuggestion (#4101 Task 1)."""

from django.test import TestCase

from world.gm.constants import GMPromptStatus
from world.gm.factories import GMPromptFactory
from world.gm.models import GMPrompt


class GMPromptRenameTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prompt = GMPromptFactory()

    def test_table_is_renamed(self):
        self.assertEqual(GMPrompt._meta.db_table, "arxii_gmprompt")

    def test_status_values_survive_the_rename(self):
        self.assertEqual(self.prompt.status, GMPromptStatus.PENDING)
        self.assertEqual(GMPromptStatus.PENDING.value, "pending")

    def test_reverse_accessor_on_sheet(self):
        self.assertIn(self.prompt, self.prompt.character_sheet.gm_prompts.all())
