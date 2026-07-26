"""The menace ModifierTarget seed (#2632 — allure's fear-facing sibling)."""

from __future__ import annotations

from django.test import TestCase, override_settings

from world.seeds.social_checks import ensure_menace_target


@override_settings(SEED_SAMPLE_CONTENT=True)
class MenaceTargetSeedTests(TestCase):
    """mechanics.ModifierCategory/ModifierTarget are content-repo-owned (#2698);
    ensure_menace_target() only invents them under SEED_SAMPLE_CONTENT — this
    test needs the real row, so it opts in."""

    def test_seeds_and_scopes_to_intimidation(self) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.mechanics.models import ModifierTarget

        intimidation = CheckTypeFactory(name="Intimidation")
        ensure_menace_target()

        target = ModifierTarget.objects.get(name="menace")
        self.assertEqual(target.target_check_type, intimidation)

    def test_idempotent_and_backfills_check_scope(self) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.mechanics.models import ModifierTarget

        ensure_menace_target()  # no Intimidation check yet
        self.assertIsNone(ModifierTarget.objects.get(name="menace").target_check_type)

        intimidation = CheckTypeFactory(name="Intimidation")
        ensure_menace_target()
        self.assertEqual(ModifierTarget.objects.get(name="menace").target_check_type, intimidation)
