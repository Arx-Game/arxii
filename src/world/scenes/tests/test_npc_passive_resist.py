"""An NPC target resists a scene social action through its Composure (#4145)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import create_resistance_check_types
from world.mechanics.models import ModifierTarget
from world.scenes.action_services import _compute_difficulty_override_for_primary
from world.scenes.factories import SceneActionRequestFactory
from world.traits.factories import StatTraitFactory
from world.traits.models import CharacterTraitValue, PointConversionRange, Trait, TraitType


class NpcPassiveResistTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
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
        CharacterTraitValue.objects.create(character=cls.weak, trait=willpower, value=10)
        CharacterTraitValue.objects.create(character=cls.strong, trait=willpower, value=40)

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()

    def _override(self, sheet: CharacterSheet) -> int | None:
        request = SceneActionRequestFactory(target_persona=sheet.primary_persona)
        return _compute_difficulty_override_for_primary(request, "")

    def test_npc_with_higher_composure_gets_higher_override(self) -> None:
        self.assertGreater(self._override(self.strong), self._override(self.weak))
