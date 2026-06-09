"""
Tests for SceneCheckModifier and its wiring into collect_check_modifiers.

SceneCheckModifier lets game authors define how a scene's surroundings affect checks
(e.g. a dark dungeon gives -10 to Perception checks, a holy ground gives +5 to Faith).
The SCENE branch is exercised via scene= in collect_check_modifiers().
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneCheckModifier


class SceneCheckModifierModelTest(TestCase):
    """Basic creation/uniqueness tests for SceneCheckModifier."""

    @classmethod
    def setUpTestData(cls):
        cls.scene = SceneFactory(name="The Dark Dungeon")
        cls.check_type = CheckTypeFactory(name="perception-scene-test")

    def test_create_scene_check_modifier(self):
        """Can create a SceneCheckModifier with a penalty."""
        mod = SceneCheckModifier.objects.create(
            scene=self.scene,
            check_type=self.check_type,
            modifier_value=-10,
        )
        assert mod.pk is not None
        assert mod.modifier_value == -10

    def test_unique_constraint_per_scene_and_check_type(self):
        """Only one SceneCheckModifier per (scene, check_type) pair."""
        from django.db import IntegrityError

        SceneCheckModifier.objects.create(
            scene=self.scene,
            check_type=self.check_type,
            modifier_value=-10,
        )
        with self.assertRaises(IntegrityError):
            SceneCheckModifier.objects.create(
                scene=self.scene,
                check_type=self.check_type,
                modifier_value=5,
            )

    def test_str_representation(self):
        """__str__ includes scene name and modifier_value."""
        mod = SceneCheckModifier(
            scene=self.scene,
            check_type=self.check_type,
            modifier_value=-10,
        )
        result = str(mod)
        assert "The Dark Dungeon" in result
        assert "-10" in result


class SceneContributionCollectionTest(TestCase):
    """Tests for the SCENE branch in collect_check_modifiers."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="perception-scene-collect")
        cls.scene = SceneFactory(name="Haunted Keep")
        cls.other_scene = SceneFactory(name="Sunny Meadow")
        SceneCheckModifier.objects.create(
            scene=cls.scene,
            check_type=cls.check_type,
            modifier_value=-2,
        )

    def setUp(self):
        self.target = ObjectDB.objects.create(db_key="SceneCollectTarget")
        self.sheet = CharacterSheetFactory(character=self.target)

    def test_scene_contribution_present(self):
        """With a SceneCheckModifier and scene=<scene>, a SCENE contribution appears."""
        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)

        scene_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        assert len(scene_contributions) == 1
        assert scene_contributions[0].value == -2

    def test_scene_contribution_label_contains_scene_name(self):
        """The SCENE contribution label includes the scene's name."""
        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)

        scene_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        assert len(scene_contributions) == 1
        assert "Haunted Keep" in scene_contributions[0].source_label

    def test_no_scene_no_contribution(self):
        """With scene=None, no SCENE contribution appears."""
        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=None)

        scene_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        assert scene_contributions == []

    def test_wrong_scene_no_contribution(self):
        """A modifier on a different scene does not appear when that scene is not passed."""
        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.other_scene)

        scene_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        assert scene_contributions == []

    def test_scene_modifier_total_incorporated(self):
        """The scene modifier is included in the breakdown total."""
        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)
        # rollmod=0, no conditions → total should equal -2
        assert breakdown.total == -2

    def test_multiple_scene_modifiers_all_appear(self):
        """When a scene has multiple check-type modifiers (different check types), each appears."""
        check_type2 = CheckTypeFactory(name="stealth-scene-multi")
        SceneCheckModifier.objects.create(
            scene=self.scene,
            check_type=check_type2,
            modifier_value=5,
        )

        breakdown1 = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)
        breakdown2 = collect_check_modifiers(self.sheet, check_type2, scene=self.scene)

        scene_contribs1 = [
            c for c in breakdown1.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        scene_contribs2 = [
            c for c in breakdown2.contributions if c.source_kind == ModifierSourceKind.SCENE
        ]
        assert len(scene_contribs1) == 1
        assert scene_contribs1[0].value == -2
        assert len(scene_contribs2) == 1
        assert scene_contribs2[0].value == 5
