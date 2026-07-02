from django.test import TestCase

from world.battles.constants import (
    BattleActionScope,
    BattleOutcome,
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
from world.magic.factories import TechniqueFactory


class BattleModelTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Siege of Test Keep")

    def test_battle_auto_creates_scene(self) -> None:
        self.assertIsNotNone(self.battle.scene_id)
        self.assertEqual(self.battle.scene.name, "Siege of Test Keep")
        self.assertFalse(self.battle.is_concluded)

    def test_battle_afk_peril_override_defaults_false(self) -> None:
        from world.battles.factories import BattleFactory

        battle = BattleFactory()
        assert battle.afk_peril_override is False

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

    def test_unit_factory_side_matches_battle(self) -> None:
        unit = BattleUnitFactory()
        self.assertEqual(unit.battle_id, unit.side.battle_id)

    def test_battle_side_covenant_defaults_to_none(self) -> None:
        side = BattleSideFactory()
        self.assertIsNone(side.covenant)

    def test_battle_side_covenant_can_be_set(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        side = BattleSideFactory(covenant=covenant)
        self.assertEqual(side.covenant_id, covenant.pk)


class BattleActionDeclarationTechniqueTests(TestCase):
    def test_declaration_requires_technique(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        technique = TechniqueFactory()
        declaration = BattleActionDeclarationFactory(technique=technique)
        self.assertEqual(declaration.technique, technique)

    def test_declaration_scope_defaults_to_unit(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        decl = BattleActionDeclarationFactory()
        self.assertEqual(decl.scope, BattleActionScope.UNIT)
        self.assertIsNone(decl.target_place)
        self.assertIsNone(decl.target_side)

    def test_declaration_scope_side_accepts_target_side(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        battle = BattleFactory()
        # DEFENDER avoids colliding with the participant subfactory's default
        # ATTACKER-role BattleSide on the same battle (unique_battle_side_role).
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        decl = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            scope=BattleActionScope.SIDE,
            target_side=side,
        )
        self.assertEqual(decl.target_side_id, side.pk)
