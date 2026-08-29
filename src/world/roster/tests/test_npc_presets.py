"""NPC statline preset service tests (#3427) — apply_npc_preset + mint_story_npc(preset=...)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.factories import (
    NPCPresetSkillLineFactory,
    NPCPresetTraitLineFactory,
    NPCStatlinePresetFactory,
)
from world.roster.services.staff_characters import (
    StaffMintError,
    apply_npc_preset,
    mint_story_npc,
)
from world.skills.models import CharacterSkillValue
from world.traits.factories import PointConversionRangeFactory
from world.traits.models import (
    STAT_DISPLAY_DIVISOR,
    CharacterTraitChange,
    CharacterTraitValue,
    TraitChangeSource,
)


class ApplyNpcPresetServiceTests(TestCase):
    """The write shape ``apply_npc_preset`` produces on a bare sheet."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.preset = NPCStatlinePresetFactory()

    def test_trait_lines_written_at_display_times_ten(self) -> None:
        line = NPCPresetTraitLineFactory(preset=self.preset, display_value=4)

        apply_npc_preset(self.sheet, self.preset)

        value = CharacterTraitValue.objects.get(character=self.sheet, trait=line.trait)
        assert value.value == 4 * STAT_DISPLAY_DIVISOR

    def test_skill_lines_write_value_plus_trait_bridge_row(self) -> None:
        line = NPCPresetSkillLineFactory(preset=self.preset, value=42)

        apply_npc_preset(self.sheet, self.preset)

        skill_value = CharacterSkillValue.objects.get(character=self.sheet, skill=line.skill)
        assert skill_value.value == 42
        # #2894 bridge: perform_check reads only CharacterTraitValue rows.
        bridge = CharacterTraitValue.objects.get(character=self.sheet, trait=line.skill.trait)
        assert bridge.value == 42

    def test_provenance_stamps_carry_npc_preset_source(self) -> None:
        trait_line = NPCPresetTraitLineFactory(preset=self.preset, display_value=5)
        skill_line = NPCPresetSkillLineFactory(preset=self.preset, value=20)

        apply_npc_preset(self.sheet, self.preset)

        changes = CharacterTraitChange.objects.filter(character_sheet=self.sheet)
        assert changes.count() == 2
        for change in changes:
            assert change.source == TraitChangeSource.NPC_PRESET
            assert change.old_value == 0

        trait_change = changes.get(trait=trait_line.trait)
        assert trait_change.new_value == 5 * STAT_DISPLAY_DIVISOR
        skill_change = changes.get(trait=skill_line.skill.trait)
        assert skill_change.new_value == 20

    def test_refuses_reapply_on_an_already_stamped_sheet(self) -> None:
        NPCPresetTraitLineFactory(preset=self.preset)
        apply_npc_preset(self.sheet, self.preset)

        second_preset = NPCStatlinePresetFactory()
        NPCPresetTraitLineFactory(preset=second_preset)
        with self.assertRaises(StaffMintError) as caught:
            apply_npc_preset(self.sheet, second_preset)
        assert "already has a preset" in caught.exception.user_message

    def test_check_pipeline_resolves_a_preset_skill(self) -> None:
        """Proves the #2894 bridge landed: a preset-applied sheet scores the
        SAME trait points as a control sheet whose bridge row was written by
        hand. Comparative, because trait_points runs raw values through
        PointConversionRange -- never identity with the skill value."""
        skill_line = NPCPresetSkillLineFactory(preset=self.preset, value=30)
        apply_npc_preset(self.sheet, self.preset)

        control_sheet = CharacterSheetFactory()
        CharacterTraitValue.objects.create(
            character=control_sheet, trait=skill_line.skill.trait, value=30
        )

        # Seed a conversion range so trait_points is nonzero -- with no rows,
        # calculate_points returns 0 and the comparison below would be vacuous.
        PointConversionRangeFactory(
            trait_type=skill_line.skill.trait.trait_type,
            min_value=1,
            max_value=100,
            points_per_level=1,
        )

        category = CheckCategoryFactory(name="npc_preset_check_category")
        check_type = CheckTypeFactory(name="npc_preset_check", category=category)
        CheckTypeTraitFactory(
            check_type=check_type, trait=skill_line.skill.trait, weight=Decimal("1.0")
        )

        preset_result = perform_check(self.sheet.character, check_type, target_difficulty=0)
        control_result = perform_check(control_sheet.character, check_type, target_difficulty=0)

        assert preset_result.trait_points > 0
        assert preset_result.trait_points == control_result.trait_points


class MintStoryNpcWithPresetServiceTests(TestCase):
    """``mint_story_npc(preset=...)`` end-to-end through the mint (#3427)."""

    def _junior_gm_account(self, username: str):
        account = AccountFactory(username=username)
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        seed_default_gm_level_caps()
        return account

    def test_mint_with_preset_applies_the_statline(self) -> None:
        account = self._junior_gm_account("preset_mint_gm")
        preset = NPCStatlinePresetFactory(name="Test Innkeeper")
        trait_line = NPCPresetTraitLineFactory(preset=preset, display_value=2)

        character = mint_story_npc(gm_account=account, name="Preset Innkeeper", preset=preset)

        value = CharacterTraitValue.objects.get(
            character=character.sheet_data, trait=trait_line.trait
        )
        assert value.value == 2 * STAT_DISPLAY_DIVISOR
        assert CharacterTraitChange.objects.filter(
            character_sheet=character.sheet_data, source=TraitChangeSource.NPC_PRESET
        ).exists()

    def test_mint_without_preset_is_unchanged(self) -> None:
        """Regression: omitting ``preset`` must not write any statline at all."""
        account = self._junior_gm_account("no_preset_mint_gm")

        character = mint_story_npc(gm_account=account, name="Blank Slate NPC")

        assert not CharacterTraitValue.objects.filter(character=character.sheet_data).exists()
        assert not CharacterTraitChange.objects.filter(
            character_sheet=character.sheet_data
        ).exists()
