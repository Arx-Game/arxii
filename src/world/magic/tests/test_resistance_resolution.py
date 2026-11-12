"""Tests for RESISTANCE pull-effect resolution (#1580).

A species-gift thread's tier-0 RESISTANCE effect mitigates the species drawback's
``ConditionResistanceModifier`` vulnerability. The two are applied on the SAME
incoming-damage subtraction in ``apply_damage_to_participant`` so they net.

- Passive (tier-0): flat ``resistance_amount`` gated by ``min_thread_level``.
- Paid pull (tier 1-3): ``resistance_amount × level_multiplier`` snapshotted on
  ``CombatPullResolvedEffect`` (combat-side; see ``world/combat/tests``).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import (
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.services import apply_condition
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, ThreadPullEffectFactory
from world.magic.services import gift_thread_resistance, resolve_pull_effects
from world.magic.specialization.services import provision_latent_gift_thread
from world.vitals.models import CharacterVitals


class _FakeStack:
    def was_cancelled(self) -> bool:
        return False


def _non_cancelling(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
    return _FakeStack()


class PassiveGiftResistanceHandlerTests(TestCase):
    """``passive_damage_type_resistance`` is flat and gated by ``min_thread_level``."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.gift = GiftFactory()
        self.fire = DamageTypeFactory(name="Fire")
        self.thread = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=self.resonance,
            tier=0,
            min_thread_level=10,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=3,
            resistance_damage_type=self.fire,
        )

    def _set_level(self, level: int) -> None:
        self.thread.level = level
        self.thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

    def test_below_threshold_inert(self) -> None:
        self._set_level(0)
        handler = self.sheet.character.threads
        self.assertEqual(handler.passive_damage_type_resistance(self.fire), 0)

    def test_at_threshold_returns_flat_amount(self) -> None:
        self._set_level(10)
        handler = self.sheet.character.threads
        self.assertEqual(handler.passive_damage_type_resistance(self.fire), 3)

    def test_passive_not_scaled_by_level(self) -> None:
        """Unlike VITAL_BONUS, passive resistance is flat — level 20 still gives 3."""
        self._set_level(20)
        handler = self.sheet.character.threads
        self.assertEqual(handler.passive_damage_type_resistance(self.fire), 3)

    def test_other_damage_type_not_matched(self) -> None:
        self._set_level(10)
        cold = DamageTypeFactory(name="Cold")
        handler = self.sheet.character.threads
        self.assertEqual(handler.passive_damage_type_resistance(cold), 0)

    def test_null_damage_type_matches_any(self) -> None:
        """A null ``resistance_damage_type`` row mitigates every damage type."""
        cold = DamageTypeFactory(name="Cold")
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=2,
            resistance_damage_type=None,
        )
        self._set_level(0)
        handler = self.sheet.character.threads
        # min_thread_level=0 null-type row contributes 2 to any type; the fire
        # row (min_thread_level=10) is still inert at level 0.
        self.assertEqual(handler.passive_damage_type_resistance(cold), 2)
        self.assertEqual(handler.passive_damage_type_resistance(self.fire), 2)


class ResolvePullEffectsResistanceScalingTests(TestCase):
    """Paid-pull RESISTANCE scales by ``level_multiplier`` (combat context)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.gift = GiftFactory()
        self.fire = DamageTypeFactory(name="Fire")
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

    def _resistance_effects(self, level: int):
        self.thread.level = level
        return [
            e
            for e in resolve_pull_effects([self.thread], tier=1, in_combat=True)
            if e.kind == EffectKind.RESISTANCE
        ]

    def test_scaled_value_is_amount_times_multiplier(self) -> None:
        # level 10 → multiplier max(1, 10//10) = 1 → 4 × 1 = 4.
        effects = self._resistance_effects(10)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].scaled_value, 4)
        self.assertEqual(effects[0].resistance_damage_type, self.fire)

    def test_scales_with_higher_level(self) -> None:
        # level 30 → multiplier max(1, 30//10) = 3 → 4 × 3 = 12.
        effects = self._resistance_effects(30)
        self.assertEqual(effects[0].scaled_value, 12)

    def test_inactive_outside_combat(self) -> None:
        self.thread.level = 30
        effects = [
            e
            for e in resolve_pull_effects([self.thread], tier=1, in_combat=False)
            if e.kind == EffectKind.RESISTANCE
        ]
        self.assertTrue(effects[0].inactive)
        self.assertEqual(effects[0].scaled_value, 0)


class GiftResistanceNettingTests(TestCase):
    """Drawback vulnerability and gift resistance net on the combat damage path."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.sheet = CharacterSheetFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, character_sheet=cls.sheet
        )
        cls.fire = DamageTypeFactory(name="Fire")
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.thread = provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.resonance)
        # +3 fire gift resistance, switching on at thread level 10.
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=cls.gift,
            resonance=cls.resonance,
            tier=0,
            min_thread_level=10,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=3,
            resistance_damage_type=cls.fire,
        )
        # -3 fire species drawback vulnerability.
        cls.drawback = ConditionTemplateFactory(name="Sun-Cursed")
        ConditionResistanceModifierFactory(
            condition=cls.drawback,
            stage=None,
            damage_type=cls.fire,
            modifier_value=-3,
        )

    def setUp(self) -> None:
        self.vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )
        character = self.sheet.character
        character.location = self.encounter.room
        character.save()
        apply_condition(character, self.drawback)

    def _set_level(self, level: int) -> None:
        self.thread.level = level
        self.thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

    def _hit(self, amount: int) -> int:
        from world.combat.services import apply_damage_to_participant

        with patch("world.combat.services.emit_event", side_effect=_non_cancelling):
            apply_damage_to_participant(self.participant, amount, damage_type=self.fire)
        self.vitals.refresh_from_db()
        return self.vitals.health

    def test_drawback_vulnerability_felt_below_threshold(self) -> None:
        """Thread below threshold: only the -3 vuln applies → 10 dmg becomes 13."""
        self._set_level(0)
        self.assertEqual(self._hit(10), 87)

    def test_gift_resistance_offsets_vulnerability_at_threshold(self) -> None:
        """Thread at threshold: +3 resistance nets the -3 vuln → 10 dmg stays 10."""
        self._set_level(10)
        self.assertEqual(self._hit(10), 90)

    def test_gift_thread_resistance_helper_nets_to_zero(self) -> None:
        self._set_level(10)
        character = self.sheet.character
        condition_mod = character.conditions.resistance_modifier(self.fire)
        gift = gift_thread_resistance(character, self.fire)
        self.assertEqual(condition_mod, -3)
        self.assertEqual(gift, 3)
        self.assertEqual(condition_mod + gift, 0)
