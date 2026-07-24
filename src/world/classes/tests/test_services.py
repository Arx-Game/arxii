from django.test import SimpleTestCase, TestCase

from world.classes.models import PathStage
from world.classes.services import stage_for_level


class StageForLevelTests(SimpleTestCase):
    def test_breakpoints(self):
        cases = {
            1: PathStage.PROSPECT,
            2: PathStage.PROSPECT,
            3: PathStage.POTENTIAL,
            5: PathStage.POTENTIAL,
            6: PathStage.PUISSANT,
            10: PathStage.PUISSANT,
            11: PathStage.TRUE,
            15: PathStage.TRUE,
            16: PathStage.GRAND,
            20: PathStage.GRAND,
            21: PathStage.TRANSCENDENT,
            30: PathStage.TRANSCENDENT,
        }
        for level, stage in cases.items():
            self.assertEqual(stage_for_level(level), stage, f"level {level}")

    def test_below_one_clamps_to_prospect(self):
        self.assertEqual(stage_for_level(0), PathStage.PROSPECT)


class SetPrimaryClassLevelTests(TestCase):
    def setUp(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.classes.factories import CharacterClassFactory, ClassStageHealthRateFactory
        from world.vitals.factories import CharacterVitalsFactory

        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        # base_max_health=None so max_health derives from level/class
        CharacterVitalsFactory(
            character_sheet=self.sheet, base_max_health=None, max_health=0, health=0
        )

        self.klass = CharacterClassFactory()
        # PROSPECT band covers levels 1-2; PUISSANT band covers levels 6-10
        ClassStageHealthRateFactory(
            character_class=self.klass, stage=PathStage.PROSPECT, health_per_level=10
        )
        ClassStageHealthRateFactory(
            character_class=self.klass, stage=PathStage.POTENTIAL, health_per_level=10
        )
        ClassStageHealthRateFactory(
            character_class=self.klass, stage=PathStage.PUISSANT, health_per_level=20
        )

    def test_set_primary_class_level_recomputes_health(self):
        from world.classes.services import set_primary_class_level
        from world.vitals.models import CharacterVitals

        set_primary_class_level(self.character, self.klass, 1)
        low = CharacterVitals.objects.get(character_sheet=self.sheet).max_health

        set_primary_class_level(self.character, self.klass, 6)
        high = CharacterVitals.objects.get(character_sheet=self.sheet).max_health

        self.assertGreater(high, low)

    def test_set_primary_class_level_upserts_row(self):
        from world.classes.services import set_primary_class_level

        ccl = set_primary_class_level(self.character, self.klass, 3)
        self.assertEqual(ccl.level, 3)
        self.assertTrue(ccl.is_primary)

    def test_set_primary_class_level_demotes_prior_primary(self):
        """Switching primary class to B demotes A — only one is_primary=True row remains."""
        from world.classes.factories import CharacterClassFactory, ClassStageHealthRateFactory
        from world.classes.models import CharacterClassLevel
        from world.classes.services import set_primary_class_level

        klass_b = CharacterClassFactory()
        ClassStageHealthRateFactory(
            character_class=klass_b, stage=PathStage.PROSPECT, health_per_level=10
        )

        # Establish class A as primary.
        set_primary_class_level(self.character, self.klass, 3)

        # Switch to class B as primary.
        ccl_b = set_primary_class_level(self.character, klass_b, 5)

        primary_rows = CharacterClassLevel.objects.filter(character=self.sheet, is_primary=True)
        self.assertEqual(primary_rows.count(), 1)
        self.assertEqual(primary_rows.first().character_class, klass_b)
        self.assertTrue(ccl_b.is_primary)

        # Class A must now be demoted.
        ccl_a = CharacterClassLevel.objects.get(character=self.sheet, character_class=self.klass)
        self.assertFalse(ccl_a.is_primary)
