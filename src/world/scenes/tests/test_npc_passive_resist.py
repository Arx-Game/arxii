"""An NPC target resists a scene social action as its level's baseline (#4145, #5093)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import create_resistance_check_types
from world.checks.test_helpers import SeededLevelLadderMixin
from world.classes.factories import CharacterClassLevelFactory
from world.mechanics.models import ModifierTarget
from world.scenes.action_services import _compute_difficulty_override_for_primary
from world.scenes.factories import SceneActionRequestFactory
from world.traits.factories import StatTraitFactory
from world.traits.models import CharacterTraitValue, PointConversionRange, Trait, TraitType


class NpcPassiveResistTests(SeededLevelLadderMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Earlier suites leave a class-level trait->ModifierTarget map pointing at rows whose
        # category was rolled back; the stat equipment walk would then chase the dead FK.
        ModifierTarget.clear_trait_cache()
        Trait.flush_instance_cache()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        create_resistance_check_types()
        willpower = StatTraitFactory(name="willpower")
        cls.weak = CharacterSheetFactory()
        cls.strong = CharacterSheetFactory()
        # An NPC has a level and no points of its own, so its trait values change nothing
        # (#5093): both carry the same willpower, and only the level differs.
        CharacterTraitValue.objects.create(character=cls.weak, trait=willpower, value=40)
        CharacterTraitValue.objects.create(character=cls.strong, trait=willpower, value=40)
        CharacterClassLevelFactory(character=cls.weak, level=1, is_primary=True)
        CharacterClassLevelFactory(character=cls.strong, level=5, is_primary=True)

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()

    def _override(self, sheet: CharacterSheet) -> int | None:
        request = SceneActionRequestFactory(target_persona=sheet.primary_persona)
        return _compute_difficulty_override_for_primary(request, "")

    def test_npc_of_a_higher_level_gets_a_higher_override(self) -> None:
        self.assertGreater(self._override(self.strong), self._override(self.weak))
