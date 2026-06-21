from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.seeds_checks import (
    MAGIC_CHECK_CATEGORY_NAME,
    ensure_character_magic_check_type,
)
from world.skills.factories import SkillFactory
from world.traits.factories import TraitFactory
from world.traits.models import TraitType


class CharacterMagicCheckTypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.other = CharacterSheetFactory()
        cls.willpower = TraitFactory(name="willpower", trait_type=TraitType.STAT)
        cls.skill = SkillFactory(trait__name="ritualism")

    def test_synthesizes_per_character_check_weighted_on_stat_and_skill(self):
        ct = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        self.assertEqual(ct.category.name, MAGIC_CHECK_CATEGORY_NAME)
        trait_names = {t.trait.name for t in ct.traits.all()}
        self.assertEqual(trait_names, {"willpower", "ritualism"})
        self.assertTrue(ct.aspects.filter(aspect__name="Arcana").exists())

    def test_distinct_rows_per_character_and_idempotent(self):
        a1 = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        a2 = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        b = ensure_character_magic_check_type(self.other, stat=self.willpower, skill=self.skill)
        self.assertEqual(a1.pk, a2.pk)
        self.assertNotEqual(a1.pk, b.pk)
