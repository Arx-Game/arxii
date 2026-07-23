"""Tests for the 8th Audere Majora eligibility gate: ClassLevelUnlock requirements (#1859)."""

from __future__ import annotations

from django.test import TestCase

from world.classes.models import CharacterClassLevel
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.magic.audere_majora import check_audere_majora_eligibility
from world.magic.tests.majora_fixtures import build_majora_world
from world.progression.models import ClassLevelUnlock, ItemRequirement


class AudereMajoraItemGateTests(TestCase):
    def setUp(self) -> None:
        (
            self.character,
            self.sheet,
            self.threshold,
            self.soulfray_stage,
            self.prospect_path,
            self.puissant_path,
        ) = self._build()
        self.passing_intensity = 20

    def _build(self):
        character, sheet, threshold, prospect_path, puissant_path, soulfray_stage = (
            build_majora_world(boundary_level=20, suffix="_item_gate_t1")
        )
        return character, sheet, threshold, soulfray_stage, prospect_path, puissant_path

    def _character_class(self):
        return CharacterClassLevel.objects.get(character=self.character.sheet_data).character_class

    def test_fail_open_with_no_authored_unlock(self) -> None:
        """No ClassLevelUnlock for boundary_level+1 -> gate does not block."""
        result = check_audere_majora_eligibility(self.character, self.passing_intensity)
        assert result is not None
        assert result.pk == self.threshold.pk

    def test_blocks_when_item_requirement_unmet(self) -> None:
        unlock = ClassLevelUnlock.objects.create(
            character_class=self._character_class(), target_level=21
        )
        template = ItemTemplateFactory()
        ItemRequirement.objects.create(class_level_unlock=unlock, item_template=template)

        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_passes_once_item_requirement_met(self) -> None:
        unlock = ClassLevelUnlock.objects.create(
            character_class=self._character_class(), target_level=21
        )
        template = ItemTemplateFactory()
        ItemRequirement.objects.create(class_level_unlock=unlock, item_template=template)
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

        # Mid-scene: the item is acquired. No re-sync step -- the very next
        # eligibility check must flip to eligible.
        ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        result = check_audere_majora_eligibility(self.character, self.passing_intensity)
        assert result is not None
        assert result.pk == self.threshold.pk
