"""Tests for Corruption foundation model additions (Magic Scope #7, Phase 5).

Covers:
- CharacterResonance corruption fields (Task 5.1)
- MagicalAlterationTemplate kind discriminator (Task 5.2)
- CorruptionConfig singleton (Task 5.3)
"""

from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.factories import (
    CharacterResonanceFactory,
    MagicalAlterationTemplateFactory,
    ResonanceFactory,
)


class CharacterResonanceCorruptionFieldsTests(TestCase):
    """CharacterResonance corruption_current / corruption_lifetime fields."""

    def test_corruption_current_default_zero(self) -> None:
        resonance = CharacterResonanceFactory()
        self.assertEqual(resonance.corruption_current, 0)

    def test_corruption_lifetime_default_zero(self) -> None:
        resonance = CharacterResonanceFactory()
        self.assertEqual(resonance.corruption_lifetime, 0)


class MagicalAlterationTemplateKindTests(TestCase):
    """MagicalAlterationTemplate.kind discriminator + CheckConstraints."""

    def test_default_kind_is_mage_scar(self) -> None:
        from world.magic.constants import AlterationKind

        template = MagicalAlterationTemplateFactory()
        self.assertEqual(template.kind, AlterationKind.MAGE_SCAR)

    def test_corruption_twist_requires_resonance_and_stage(self) -> None:
        from world.magic.constants import AlterationKind

        with self.assertRaises(IntegrityError):
            MagicalAlterationTemplateFactory(
                kind=AlterationKind.CORRUPTION_TWIST,
                resonance=None,
                stage_threshold=None,
            )

    def test_mage_scar_rejects_resonance_and_stage(self) -> None:
        from world.magic.constants import AlterationKind

        with self.assertRaises(IntegrityError):
            MagicalAlterationTemplateFactory(
                kind=AlterationKind.MAGE_SCAR,
                resonance=ResonanceFactory(),
                stage_threshold=2,
            )

    def test_corruption_twist_with_resonance_and_stage_ok(self) -> None:
        from world.magic.constants import AlterationKind

        template = MagicalAlterationTemplateFactory(
            kind=AlterationKind.CORRUPTION_TWIST,
            resonance=ResonanceFactory(),
            stage_threshold=2,
        )
        self.assertIsNotNone(template.pk)


class CorruptionConfigTests(TestCase):
    """CorruptionConfig singleton creation and retrieval."""

    def test_singleton_lazy_create(self) -> None:
        from world.magic.services.corruption import get_corruption_config

        config = get_corruption_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.abyssal_coefficient, 10)
        self.assertEqual(config.celestial_coefficient, 0)

    def test_singleton_returns_same_row(self) -> None:
        from world.magic.services.corruption import get_corruption_config

        config_a = get_corruption_config()
        config_b = get_corruption_config()
        self.assertEqual(config_a.pk, config_b.pk)
        self.assertEqual(config_a.pk, 1)
