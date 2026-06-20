from django.test import SimpleTestCase

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
