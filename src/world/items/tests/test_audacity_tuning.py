"""Tests for the AudacityTuning singleton + its lazy-create/fallback contract (#2029)."""

from decimal import Decimal

from django.test import TestCase

from world.items.constants import StyleAudacity
from world.items.models import AudacityTuning
from world.items.services.styles import audacity_multiplier_for, get_audacity_tuning


class AudacityTuningDefaultsTests(TestCase):
    """The lazy-created singleton's default multipliers match the authored tiers."""

    def test_get_audacity_tuning_lazy_creates_singleton(self) -> None:
        self.assertFalse(AudacityTuning.objects.exists())
        cfg = get_audacity_tuning()
        self.assertEqual(cfg.pk, 1)
        self.assertTrue(AudacityTuning.objects.exists())

    def test_get_audacity_tuning_is_idempotent(self) -> None:
        first = get_audacity_tuning()
        second = get_audacity_tuning()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AudacityTuning.objects.count(), 1)

    def test_default_multipliers_ascend_with_audacity(self) -> None:
        """Fallback (no row edits) — multiplier_for() should never crash and should
        rank UNDERSTATED < EXPRESSIVE < BOLD < OUTRAGEOUS by default.
        """
        cfg = get_audacity_tuning()
        understated = cfg.multiplier_for(StyleAudacity.UNDERSTATED)
        expressive = cfg.multiplier_for(StyleAudacity.EXPRESSIVE)
        bold = cfg.multiplier_for(StyleAudacity.BOLD)
        outrageous = cfg.multiplier_for(StyleAudacity.OUTRAGEOUS)

        self.assertEqual(understated, Decimal("0.75"))
        self.assertEqual(expressive, Decimal("1.00"))
        self.assertEqual(bold, Decimal("1.35"))
        self.assertEqual(outrageous, Decimal("1.75"))
        self.assertLess(understated, expressive)
        self.assertLess(expressive, bold)
        self.assertLess(bold, outrageous)

    def test_multiplier_for_unrecognized_value_falls_back_to_expressive(self) -> None:
        """An out-of-range int must not crash — falls back to expressive_mult."""
        cfg = get_audacity_tuning()
        self.assertEqual(cfg.multiplier_for(999), cfg.expressive_mult)

    def test_staff_edit_is_read_by_multiplier_for(self) -> None:
        cfg = get_audacity_tuning()
        cfg.bold_mult = Decimal("2.50")
        cfg.save(update_fields=["bold_mult"])
        cfg.refresh_from_db()
        self.assertEqual(cfg.multiplier_for(StyleAudacity.BOLD), Decimal("2.50"))


class AudacityMultiplierForStyleTests(TestCase):
    """``audacity_multiplier_for(style)`` resolves through the style's own tier."""

    def test_multiplier_for_style_reads_its_audacity_tier(self) -> None:
        from world.items.factories import StyleFactory

        bold_style = StyleFactory(name="AudacityTestBold", audacity=StyleAudacity.BOLD)
        self.assertEqual(audacity_multiplier_for(bold_style), Decimal("1.35"))

    def test_multiplier_for_style_default_audacity_is_expressive(self) -> None:
        from world.items.factories import StyleFactory

        default_style = StyleFactory(name="AudacityTestDefault")
        self.assertEqual(default_style.audacity, StyleAudacity.EXPRESSIVE)
        self.assertEqual(audacity_multiplier_for(default_style), Decimal("1.00"))
