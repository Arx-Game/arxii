"""Tests for expire_pulls_for_round (Spec A §3.8 + §7.4 Phase 13).

Covers the round-advance expiry path:

- ``expire_pulls_for_round`` deletes stale CombatPull rows (and their
  resolved-effect children via cascade).
- ``CharacterCombatPullHandler`` caches are invalidated for every affected
  participant so ``active_pull_vital_bonuses`` picks up the change.
- ``recompute_max_health_with_threads`` runs per affected participant so
  MAX_HEALTH bolsters drop off via the clamp-not-injure path.
- ``begin_declaration_phase`` wires the call after ``round_number`` advances.
"""

from __future__ import annotations

from django.db import transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatPullFactory,
    CombatPullResolvedEffectFactory,
)
from world.combat.models import CombatPull, CombatPullResolvedEffect
from world.combat.services import begin_declaration_phase, expire_pulls_for_round
from world.magic.constants import EffectKind, VitalBonusTarget
from world.vitals.models import CharacterVitals


class ExpirePullsForRoundTests(TestCase):
    """Direct tests on expire_pulls_for_round (no round advance)."""

    def test_stale_pulls_deleted(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=3)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        # Stale: round 2 vs encounter round 3.
        stale_pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=2,
        )
        # Fresh: matches current round.
        fresh_pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=3,
        )

        expire_pulls_for_round(encounter)

        self.assertFalse(CombatPull.objects.filter(pk=stale_pull.pk).exists())
        self.assertTrue(CombatPull.objects.filter(pk=fresh_pull.pk).exists())

    def test_cascaded_resolved_effects_deleted(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=2)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        stale_pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
        )
        CombatPullResolvedEffectFactory(pull=stale_pull)
        CombatPullResolvedEffectFactory(pull=stale_pull)

        self.assertEqual(CombatPullResolvedEffect.objects.count(), 2)
        expire_pulls_for_round(encounter)
        self.assertEqual(CombatPullResolvedEffect.objects.count(), 0)

    def test_expiry_recomputes_max_health_clamps_not_injures(self) -> None:
        """Pull expiry removes bolster without pushing current below prior level.

        Spec A §3.8 clamp-not-injure. This test is the canonical scenario:
          - base_max_health=100, stale MAX_HEALTH pull +20 persisted while
            max_health was already 120.
          - Character took 25 damage → current=95.
          - Pull expires on round advance → max back to 100, current stays 95.
        """
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=2)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        vitals = CharacterVitals.objects.create(
            character_sheet=sheet,
            health=95,
            max_health=120,  # stale bolstered value.
            base_max_health=100,
        )
        # Stale pull with a MAX_HEALTH +20 resolved effect — about to expire.
        stale_pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=1,
        )
        CombatPullResolvedEffectFactory(
            pull=stale_pull,
            kind=EffectKind.VITAL_BONUS,
            authored_value=10,
            level_multiplier=2,
            scaled_value=20,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )

        expire_pulls_for_round(encounter)

        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 100)
        self.assertEqual(vitals.health, 95)

    def test_no_stale_pulls_is_noop(self) -> None:
        """Zero stale rows → nothing deleted, no recompute, no crash."""
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(round_number=3)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        # Only a fresh pull — nothing to expire.
        fresh = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=3,
        )

        expire_pulls_for_round(encounter)

        self.assertTrue(CombatPull.objects.filter(pk=fresh.pk).exists())

    def test_expiry_scoped_to_this_encounter(self) -> None:
        """Stale pulls in a different encounter are NOT deleted."""
        sheet = CharacterSheetFactory()
        enc1 = CombatEncounterFactory(round_number=3)
        enc2 = CombatEncounterFactory(round_number=3)
        p1 = CombatParticipantFactory(encounter=enc1, character_sheet=sheet)
        p2 = CombatParticipantFactory(encounter=enc2, character_sheet=sheet)
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        enc1_stale = CombatPullFactory(
            participant=p1,
            encounter=enc1,
            round_number=2,
        )
        enc2_stale = CombatPullFactory(
            participant=p2,
            encounter=enc2,
            round_number=2,
        )

        expire_pulls_for_round(enc1)

        # enc1's stale pull is gone; enc2's survives.
        self.assertFalse(CombatPull.objects.filter(pk=enc1_stale.pk).exists())
        self.assertTrue(CombatPull.objects.filter(pk=enc2_stale.pk).exists())


class BeginDeclarationPhaseExpiryTests(TestCase):
    """begin_declaration_phase must call expire_pulls_for_round after advancing."""

    def test_round_advance_expires_stale_pulls(self) -> None:
        sheet = CharacterSheetFactory()
        encounter = CombatEncounterFactory(
            round_number=2,
            status=EncounterStatus.BETWEEN_ROUNDS,
        )
        # begin_declaration_phase requires at least one active opponent.
        CombatOpponentFactory(encounter=encounter)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        # Stale pull (round 2) — after advance round becomes 3, so this is stale.
        stale_pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=2,
        )

        with transaction.atomic():
            begin_declaration_phase(encounter)

        encounter.refresh_from_db()
        self.assertEqual(encounter.round_number, 3)
        self.assertFalse(CombatPull.objects.filter(pk=stale_pull.pk).exists())
