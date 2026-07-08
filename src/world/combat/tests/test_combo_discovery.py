"""Tests for the combo discovery ceremony service."""

from __future__ import annotations

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.combo_discovery import fire_combo_discovery
from world.combat.constants import ComboLearningMethod
from world.combat.factories import ComboDefinitionFactory, ComboSlotFactory
from world.combat.models import ComboLearning
from world.magic.factories import EffectTypeFactory, ResonanceFactory


class FireComboDiscoveryTests(TestCase):
    """Tests for the combo discovery ceremony."""

    def test_writes_combo_learning_for_each_participant(self) -> None:
        """ComboLearning rows are created for all participants."""
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(combo=combo)
        sheets = [CharacterSheetFactory() for _ in range(3)]

        fire_combo_discovery(combo=combo, participant_sheets=sheets)

        for sheet in sheets:
            learning = ComboLearning.objects.get(combo=combo, character_sheet=sheet)
            self.assertEqual(learning.learned_via, ComboLearningMethod.COMBAT)

    def test_idempotent_on_second_call(self) -> None:
        """Calling fire_combo_discovery twice does not create duplicate rows."""
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(combo=combo)
        sheet = CharacterSheetFactory()

        fire_combo_discovery(combo=combo, participant_sheets=[sheet])
        fire_combo_discovery(combo=combo, participant_sheets=[sheet])

        self.assertEqual(
            ComboLearning.objects.filter(combo=combo, character_sheet=sheet).count(),
            1,
        )

    def test_grants_resonance_when_slot_has_requirement(self) -> None:
        """Resonance is granted when a slot has a resonance_requirement."""
        from world.magic.models import CharacterResonance

        resonance = ResonanceFactory()
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        effect_type = EffectTypeFactory()
        ComboSlotFactory(
            combo=combo,
            required_action_type=effect_type,
            resonance_requirement=resonance,
        )
        sheet = CharacterSheetFactory()

        fire_combo_discovery(combo=combo, participant_sheets=[sheet])

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertGreater(cr.balance, 0)

    def test_skips_resonance_when_no_slot_requirement(self) -> None:
        """No resonance grant when no slot has a resonance_requirement."""
        from world.magic.models import CharacterResonance

        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        effect_type = EffectTypeFactory()
        ComboSlotFactory(combo=combo, required_action_type=effect_type)
        sheet = CharacterSheetFactory()

        fire_combo_discovery(combo=combo, participant_sheets=[sheet])

        self.assertFalse(CharacterResonance.objects.filter(character_sheet=sheet).exists())

    def test_fires_achievement_ceremony_when_configured(self) -> None:
        """Achievement is granted when discovery_achievement + ceremony copy are set."""
        from world.achievements.models import CharacterAchievement

        achievement = AchievementFactory()
        combo = ComboDefinitionFactory(
            discoverable_via_combat=True,
            discovery_first_body="A new combo has been discovered!",
            discovery_personal_body="You discovered a combo!",
        )
        combo.discovery_achievement = achievement
        combo.save()
        effect_type = EffectTypeFactory()
        ComboSlotFactory(combo=combo, required_action_type=effect_type)
        sheet = CharacterSheetFactory()

        fire_combo_discovery(combo=combo, participant_sheets=[sheet])

        self.assertTrue(
            CharacterAchievement.objects.filter(
                achievement=achievement,
                character_sheet=sheet,
            ).exists()
        )
