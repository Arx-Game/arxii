from django.db import IntegrityError
from django.test import TestCase

from world.battles.constants import (
    BattleOutcome,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitComposition,
    UnitQuality,
)
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import (
    BattleUnit,
    TechniqueCompositionAffinity,
    TerrainCompositionEffect,
)
from world.character_sheets.factories import CharacterSheetFactory
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
            descriptor="zombies-on-nightmares",
            strength=80,
        )
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)
        self.assertEqual(self.battle.sides.count(), 1)
        self.assertEqual(defender.units.count(), 1)
        self.assertEqual(self.battle.outcome, BattleOutcome.UNRESOLVED)

    def test_unit_factory_side_matches_battle(self) -> None:
        unit = BattleUnitFactory()
        self.assertEqual(unit.battle_id, unit.side.battle_id)


class BattleActionDeclarationTechniqueTests(TestCase):
    def test_declaration_requires_technique(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        technique = TechniqueFactory()
        declaration = BattleActionDeclarationFactory(technique=technique)
        self.assertEqual(declaration.technique, technique)


class BattleUnitTaxonomyTests(TestCase):
    def test_defaults(self) -> None:
        unit = BattleUnitFactory()
        self.assertEqual(unit.composition, UnitComposition.IRREGULAR)
        self.assertEqual(unit.quality, UnitQuality.TRAINED)
        self.assertIsNone(unit.commander)
        self.assertIsNone(unit.summoned_by)

    def test_commander_set_null_on_character_sheet_delete(self) -> None:
        commander = CharacterSheetFactory()
        unit = BattleUnitFactory(commander=commander)
        commander.character.delete()
        # Flush identity mapper cache so refresh_from_db picks up SET_NULL change
        BattleUnit.flush_instance_cache()
        unit.refresh_from_db()
        self.assertIsNone(unit.commander)


class TechniqueCompositionAffinityTests(TestCase):
    def test_unique_per_technique_composition(self) -> None:
        technique = TechniqueFactory()
        TechniqueCompositionAffinity.objects.create(
            technique=technique, composition=UnitComposition.CAVALRY, modifier=15
        )
        with self.assertRaises(IntegrityError):
            TechniqueCompositionAffinity.objects.create(
                technique=technique, composition=UnitComposition.CAVALRY, modifier=-5
            )


class TerrainCompositionEffectTests(TestCase):
    def test_unique_per_terrain_composition(self) -> None:
        TerrainCompositionEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, composition=UnitComposition.CAVALRY, modifier=15
        )
        with self.assertRaises(IntegrityError):
            TerrainCompositionEffect.objects.create(
                terrain_type=TerrainType.DIFFICULT, composition=UnitComposition.CAVALRY, modifier=5
            )
