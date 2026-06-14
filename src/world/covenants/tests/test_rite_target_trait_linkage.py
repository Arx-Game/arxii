"""Task A1 (#783): rite-seeded stat ModifierTargets must link their Trait.

``wire_covenant_rite_content`` creates stat ``ModifierTarget`` rows for the
covenant-rite buffs. Those targets must set ``target_trait`` so that
``ModifierTarget.get_for_trait`` (which filters ``target_trait__isnull=False``)
can resolve them — otherwise the buffs never reach the trait cache.

The canonical stat Traits are not auto-seeded in a fresh test DB, so this test
seeds willpower/composure/stability the same way the trait tests do
(``Trait.objects.get_or_create`` with ``TraitType.STAT``).
"""

from __future__ import annotations

from django.test import TestCase

from world.covenants.factories import wire_covenant_rite_content
from world.mechanics.models import ModifierTarget
from world.traits.models import Trait, TraitCategory, TraitType


class RiteStatTargetTraitLinkageTest(TestCase):
    """Seeded stat ModifierTargets link to their canonical Trait."""

    def setUp(self) -> None:
        # Canonical stat Traits are not auto-present in a fresh test DB; seed
        # them here so Trait.get_by_name resolves inside the wire helper.
        for stat_name in ("willpower", "composure", "stability"):
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": TraitCategory.MENTAL,
                    "description": f"{stat_name.capitalize()} stat.",
                },
            )

    def test_seeded_stat_targets_have_target_trait_set(self) -> None:
        wire_covenant_rite_content()
        for stat_name in ("willpower", "composure", "stability"):
            target = ModifierTarget.objects.get(category__name="stat", name=stat_name)
            self.assertIsNotNone(
                target.target_trait,
                f"stat ModifierTarget {stat_name!r} must link its Trait (no orphan)",
            )
            self.assertEqual(target.target_trait, Trait.get_by_name(stat_name))
