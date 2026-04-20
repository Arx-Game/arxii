"""Tests for Spec A §7.2 Step 4: Magical Scars → Mage Scars display rename.

Rename is display-only. Class names and DB table names remain unchanged;
verbose_name / verbose_name_plural carry the new player-facing label.
"""

from django.test import TestCase


class MageScarsRenameTests(TestCase):
    """Verify verbose_name reflects the Mage Scars rename."""

    def test_template_verbose_name(self) -> None:
        from world.magic.models import (
            MagicalAlterationTemplate,
        )

        self.assertEqual(MagicalAlterationTemplate._meta.verbose_name, "mage scar")

    def test_template_verbose_name_plural(self) -> None:
        from world.magic.models import (
            MagicalAlterationTemplate,
        )

        self.assertEqual(MagicalAlterationTemplate._meta.verbose_name_plural, "mage scars")

    def test_pending_alteration_verbose_name(self) -> None:
        from world.magic.models import (
            PendingAlteration,
        )

        self.assertIn("Mage Scar", PendingAlteration._meta.verbose_name_plural.title())
