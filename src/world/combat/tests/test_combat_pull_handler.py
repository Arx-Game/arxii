"""Tests for CharacterCombatPullHandler (Spec A §3.7)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatPullFactory,
    CombatPullResolvedEffectFactory,
)
from world.magic.constants import EffectKind, VitalBonusTarget


class CharacterCombatPullHandlerTests(TestCase):
    def test_active_returns_only_current_round_pulls(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=3)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        # Active: round_number == encounter.round_number (3).
        active_pull = CombatPullFactory(participant=participant, round_number=3)
        # Stale (would be deleted by expire_pulls_for_round in Phase 13).
        CombatPullFactory(participant=participant, round_number=2)

        active = sheet.character.combat_pulls.active()
        self.assertEqual({p.pk for p in active}, {active_pull.pk})

    def test_active_excludes_other_characters(self) -> None:
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=1)
        part_a = CombatParticipantFactory(encounter=encounter, character_sheet=sheet_a)
        part_b = CombatParticipantFactory(encounter=encounter, character_sheet=sheet_b)
        CombatPullFactory(participant=part_a, round_number=1)
        CombatPullFactory(participant=part_b, round_number=1)

        self.assertEqual(len(sheet_a.character.combat_pulls.active()), 1)

    def test_active_for_encounter_filters_by_encounter(self) -> None:
        sheet = CharacterSheetFactory()
        enc1 = CombatEncounterFactory(round_number=1)
        enc2 = CombatEncounterFactory(round_number=1)
        p1 = CombatParticipantFactory(encounter=enc1, character_sheet=sheet)
        p2 = CombatParticipantFactory(encounter=enc2, character_sheet=sheet)
        CombatPullFactory(participant=p1, round_number=1)
        CombatPullFactory(participant=p2, round_number=1)

        self.assertEqual(len(sheet.character.combat_pulls.active_for_encounter(enc1)), 1)

    def test_active_pull_vital_bonuses_sums_scaled_value(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        pull = CombatPullFactory(participant=participant, round_number=1)
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=5,
            vital_target=VitalBonusTarget.MAX_HEALTH,
            authored_value=5,
            level_multiplier=1,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=3,
            vital_target=VitalBonusTarget.MAX_HEALTH,
            authored_value=3,
            level_multiplier=1,
        )
        # Different target — should not contribute to MAX_HEALTH total.
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=11,
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
            authored_value=11,
            level_multiplier=1,
        )

        total = sheet.character.combat_pulls.active_pull_vital_bonuses(
            VitalBonusTarget.MAX_HEALTH,
        )
        self.assertEqual(total, 8)

    def test_invalidate_clears_cache(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CombatPullFactory(participant=participant, round_number=1)
        # Warm cache: prove subsequent reads are zero queries.
        sheet.character.combat_pulls.active()
        with self.assertNumQueries(0):
            sheet.character.combat_pulls.active()
        sheet.character.combat_pulls.invalidate()
        # After invalidate, reads must hit the DB again.
        with self.assertNumQueries(1):
            sheet.character.combat_pulls.active()
