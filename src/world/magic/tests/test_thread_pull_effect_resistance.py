"""ThreadPullEffect EffectKind.RESISTANCE — payload columns + constraint tests.

Verifies:
  1. RESISTANCE requires resistance_amount (null → ValidationError via full_clean()).
  2. RESISTANCE + a DamageType FK is valid (optional FK).
  3. RESISTANCE with flat_bonus_amount set → ValidationError (exclusivity).
  4. FLAT_BONUS with resistance_amount set → ValidationError (existing constraints extended).

Uses FactoryBoy + setUpTestData. Rows are constructed directly (no RESISTANCE trait
in ThreadPullEffectFactory yet — that lives in Task 6 seeding).
"""

from typing import ClassVar

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.conditions.factories import DamageTypeFactory
from world.conditions.models import DamageType
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadPullEffectFactory
from world.magic.models import Resonance, ThreadPullEffect


class ResistancePayloadTests(TestCase):
    """ThreadPullEffect RESISTANCE kind — payload validation."""

    resonance: ClassVar[Resonance]
    damage_type: ClassVar[DamageType]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.damage_type = DamageTypeFactory()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build(self, **kwargs) -> ThreadPullEffect:
        """Build an unsaved ThreadPullEffect with RESISTANCE defaults."""
        defaults: dict = {
            "target_kind": TargetKind.TRAIT,
            "resonance": self.resonance,
            "tier": 0,
            "min_thread_level": 0,
            "effect_kind": EffectKind.RESISTANCE,
            "resistance_amount": 5,
        }
        defaults.update(kwargs)
        return ThreadPullEffect(**defaults)

    # ------------------------------------------------------------------
    # test_resistance_requires_amount
    # ------------------------------------------------------------------

    def test_resistance_requires_amount(self) -> None:
        """RESISTANCE with resistance_amount=None → full_clean() raises ValidationError."""
        obj = self._build(resistance_amount=None)
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        errors = ctx.exception.message_dict
        self.assertIn("resistance_amount", errors)

    # ------------------------------------------------------------------
    # test_resistance_valid
    # ------------------------------------------------------------------

    def test_resistance_valid_without_damage_type(self) -> None:
        """RESISTANCE with resistance_amount set, no damage_type → valid."""
        obj = self._build(resistance_amount=10, resistance_damage_type=None)
        obj.full_clean()  # must not raise

    def test_resistance_valid_with_damage_type(self) -> None:
        """RESISTANCE with resistance_amount + DamageType FK → valid."""
        obj = self._build(resistance_amount=10, resistance_damage_type=self.damage_type)
        obj.full_clean()  # must not raise

    # ------------------------------------------------------------------
    # test_resistance_forbids_other_payloads
    # ------------------------------------------------------------------

    def test_resistance_forbids_flat_bonus_amount(self) -> None:
        """RESISTANCE + flat_bonus_amount set → ValidationError."""
        obj = self._build(flat_bonus_amount=5)
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("flat_bonus_amount", ctx.exception.message_dict)

    def test_resistance_forbids_intensity_bump_amount(self) -> None:
        """RESISTANCE + intensity_bump_amount set → ValidationError."""
        obj = self._build(intensity_bump_amount=3)
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("intensity_bump_amount", ctx.exception.message_dict)

    # ------------------------------------------------------------------
    # test_flat_bonus_forbids_resistance_columns
    # ------------------------------------------------------------------

    def test_flat_bonus_forbids_resistance_amount(self) -> None:
        """FLAT_BONUS with resistance_amount → ValidationError (existing constraint extended)."""
        # Use a fresh resonance so the unique constraint doesn't collide with
        # ThreadPullEffectFactory defaults.
        resonance = ResonanceFactory()
        obj = ThreadPullEffect(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
            resistance_amount=3,  # must be forbidden
        )
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("resistance_amount", ctx.exception.message_dict)

    def test_flat_bonus_default_factory_still_valid(self) -> None:
        """Existing ThreadPullEffectFactory (FLAT_BONUS) remains valid after constraint changes."""
        # Use create() so SubFactory resonance has a PK for FK validation.
        obj = ThreadPullEffectFactory()
        obj.full_clean()  # must not raise
