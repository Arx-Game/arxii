"""The poise ModifierTarget seed (#4754): Composure-scoped, the narrow keep-your-cool lever."""

from __future__ import annotations

from django.test import TestCase, override_settings

from world.seeds.social_checks import POISE_DESCRIPTION, ensure_poise_target


@override_settings(SEED_SAMPLE_CONTENT=True)
class PoiseTargetSeedTests(TestCase):
    """ModifierTarget rows are content-repo-owned (#2698); the seed only invents them under
    SEED_SAMPLE_CONTENT, so this test opts in."""

    def test_seeds_and_scopes_to_composure(self) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.mechanics.models import ModifierTarget

        composure = CheckTypeFactory(name="Composure")
        ensure_poise_target()

        target = ModifierTarget.objects.get(name="poise")
        self.assertEqual(target.target_check_type, composure)
        self.assertEqual(target.category.name, "roll_modifier")
        self.assertEqual(target.description, POISE_DESCRIPTION)

    def test_idempotent_and_backfills_check_scope(self) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.mechanics.models import ModifierTarget

        ensure_poise_target()  # no Composure check yet
        self.assertIsNone(ModifierTarget.objects.get(name="poise").target_check_type)

        composure = CheckTypeFactory(name="Composure")
        ensure_poise_target()
        ensure_poise_target()
        self.assertEqual(ModifierTarget.objects.filter(name="poise").count(), 1)
        self.assertEqual(ModifierTarget.objects.get(name="poise").target_check_type, composure)
