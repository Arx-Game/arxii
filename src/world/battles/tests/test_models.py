from django.test import TestCase

from world.battles.constants import BattleOutcome, BattleSideRole, BattleUnitStatus
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)


class BattleModelTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Siege of Test Keep")

    def test_battle_auto_creates_scene(self) -> None:
        self.assertIsNotNone(self.battle.scene_id)
        self.assertEqual(self.battle.scene.name, "Siege of Test Keep")
        self.assertFalse(self.battle.is_concluded)

    def test_sides_and_units(self) -> None:
        defender = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        place = BattlePlaceFactory(battle=self.battle, name="The Main Gates")
        unit = BattleUnitFactory(
            battle=self.battle,
            side=defender,
            place=place,
            unit_type="zombies-on-nightmares",
            strength=80,
        )
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)
        self.assertEqual(self.battle.sides.count(), 1)
        self.assertEqual(defender.units.count(), 1)
        self.assertEqual(self.battle.outcome, BattleOutcome.UNRESOLVED)
