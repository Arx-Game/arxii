"""Combat-side RESISTANCE pull resolution (#1580).

Covers the paid-pull half of the species-gift resistance feature:

- ``CharacterCombatPullHandler.active_pull_resistance`` reads RESISTANCE snapshots
  filtered by damage type.
- ``spend_resonance_for_pull`` commits a tier-1 RESISTANCE pull on a GIFT thread
  and snapshots ``scaled_value = resistance_amount × level_multiplier`` onto
  ``CombatPullResolvedEffect`` — larger at higher thread level.
- The pulled resistance reduces incoming damage on ``apply_damage_to_participant``.
- Non-regression: an existing FLAT_BONUS pull still resolves unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatPullFactory,
    CombatPullResolvedEffectFactory,
)
from world.combat.models import CombatPull, CombatPullResolvedEffect
from world.conditions.factories import DamageTypeFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.services import spend_resonance_for_pull
from world.magic.specialization.services import provision_latent_gift_thread
from world.magic.types import PullActionContext
from world.vitals.models import CharacterVitals


class _FakeStack:
    def was_cancelled(self) -> bool:
        return False


def _non_cancelling(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
    return _FakeStack()


class ActivePullResistanceReaderTests(TestCase):
    """``active_pull_resistance`` sums matching RESISTANCE snapshots."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.fire = DamageTypeFactory(name="Fire")
        self.encounter = CombatEncounterFactory(round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.pull = CombatPullFactory(
            participant=self.participant, encounter=self.encounter, round_number=1
        )

    def test_matching_resistance_summed(self) -> None:
        CombatPullResolvedEffectFactory(
            pull=self.pull,
            kind=EffectKind.RESISTANCE,
            authored_value=4,
            level_multiplier=3,
            scaled_value=12,
            resistance_damage_type=self.fire,
        )
        self.assertEqual(self.sheet.character.combat_pulls.active_pull_resistance(self.fire), 12)

    def test_other_damage_type_not_summed(self) -> None:
        cold = DamageTypeFactory(name="Cold")
        CombatPullResolvedEffectFactory(
            pull=self.pull,
            kind=EffectKind.RESISTANCE,
            authored_value=4,
            level_multiplier=3,
            scaled_value=12,
            resistance_damage_type=self.fire,
        )
        self.assertEqual(self.sheet.character.combat_pulls.active_pull_resistance(cold), 0)

    def test_null_damage_type_matches_any(self) -> None:
        cold = DamageTypeFactory(name="Cold")
        CombatPullResolvedEffectFactory(
            pull=self.pull,
            kind=EffectKind.RESISTANCE,
            authored_value=5,
            level_multiplier=1,
            scaled_value=5,
            resistance_damage_type=None,
        )
        self.assertEqual(self.sheet.character.combat_pulls.active_pull_resistance(cold), 5)
        self.assertEqual(self.sheet.character.combat_pulls.active_pull_resistance(self.fire), 5)


class PulledResistanceCommitTests(TestCase):
    """``spend_resonance_for_pull`` commits a RESISTANCE pull on a GIFT thread."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=self.sheet.character, current=10, maximum=10)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        self.fire = DamageTypeFactory(name="Fire")
        self.gift = GiftFactory()
        self.thread = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=4,
            resistance_damage_type=self.fire,
        )

    def _commit_at_level(self, level: int) -> None:
        self.thread.level = level
        self.thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        ctx = PullActionContext(combat_encounter=encounter, participant=participant)
        spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=ctx,
        )

    def test_snapshot_scales_with_level(self) -> None:
        self._commit_at_level(30)
        snap = CombatPullResolvedEffect.objects.get(kind=EffectKind.RESISTANCE)
        # level 30 → multiplier max(1, 30//10) = 3 → 4 × 3 = 12.
        self.assertEqual(snap.scaled_value, 12)
        self.assertEqual(snap.authored_value, 4)
        self.assertEqual(snap.level_multiplier, 3)
        self.assertEqual(snap.resistance_damage_type_id, self.fire.pk)
        self.assertEqual(snap.source_thread_id, self.thread.pk)

    def test_higher_level_yields_larger_reduction(self) -> None:
        low = self.sheet.character  # warm handle
        self._commit_at_level(10)
        reduction_low = low.combat_pulls.active_pull_resistance(self.fire)
        CombatPull.objects.all().delete()
        self.sheet.character.combat_pulls.invalidate()
        self._commit_at_level(30)
        reduction_high = self.sheet.character.combat_pulls.active_pull_resistance(self.fire)
        # level 10 → 4×1 = 4; level 30 → 4×3 = 12.
        self.assertEqual(reduction_low, 4)
        self.assertEqual(reduction_high, 12)
        self.assertGreater(reduction_high, reduction_low)


class PulledResistanceDamagePathTests(TestCase):
    """A committed RESISTANCE snapshot reduces incoming combat damage."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.fire = DamageTypeFactory(name="Fire")
        self.encounter = CombatEncounterFactory(round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        character = self.sheet.character
        character.location = self.encounter.room
        character.save()
        pull = CombatPullFactory(
            participant=self.participant, encounter=self.encounter, round_number=1
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.RESISTANCE,
            authored_value=4,
            level_multiplier=3,
            scaled_value=12,
            resistance_damage_type=self.fire,
        )

    def test_pulled_resistance_reduces_damage(self) -> None:
        from world.combat.services import apply_damage_to_participant

        with patch("world.combat.services.emit_event", side_effect=_non_cancelling):
            apply_damage_to_participant(self.participant, 20, damage_type=self.fire)
        self.vitals.refresh_from_db()
        # 20 incoming − 12 pulled resistance = 8 damage → health 92.
        self.assertEqual(self.vitals.health, 92)


class FlatBonusPullNonRegressionTests(TestCase):
    """A FLAT_BONUS pull resolves unchanged after the RESISTANCE additions."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=self.sheet.character, current=10, maximum=10)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

    def test_flat_bonus_pull_still_commits(self) -> None:
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=3,
        )
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        ctx = PullActionContext(
            combat_encounter=encounter,
            participant=participant,
            involved_traits=(thread.target_trait_id,),
        )
        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )
        self.assertEqual(result.resonance_spent, 2)
        flat = [e for e in result.resolved_effects if e.kind == EffectKind.FLAT_BONUS]
        self.assertTrue(flat)
        self.assertFalse(
            CombatPullResolvedEffect.objects.filter(kind=EffectKind.RESISTANCE).exists()
        )
