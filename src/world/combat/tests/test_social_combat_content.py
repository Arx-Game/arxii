"""Tests for the social-combat content seed (#2015)."""

from django.test import TestCase

from world.combat.social_combat_content import ensure_social_combat_content


class SocialCombatContentSeedTests(TestCase):
    def test_seed_creates_four_check_types(self) -> None:
        from world.checks.models import CheckType

        ensure_social_combat_content()
        for name in ("Rally", "Demoralize", "Taunt", "Parley"):
            self.assertTrue(
                CheckType.objects.filter(name=name, is_active=True).exists(),
                f"CheckType {name!r} not seeded",
            )

    def test_demoralize_composition_is_stat_plus_skill_plus_spec(self) -> None:
        from world.checks.models import (
            CheckType,
            CheckTypeSpecialization,
            CheckTypeTrait,
        )

        ensure_social_combat_content()
        ct = CheckType.objects.get(name="Demoralize")
        traits = {t.trait.name for t in CheckTypeTrait.objects.filter(check_type=ct)}
        self.assertIn("presence", traits)
        self.assertIn("Persuasion", traits)
        specs = {
            s.specialization.name for s in CheckTypeSpecialization.objects.filter(check_type=ct)
        }
        self.assertIn("Intimidation", specs)

    def test_seed_creates_inspired_condition(self) -> None:
        from world.conditions.models import ConditionTemplate

        ensure_social_combat_content()
        self.assertTrue(ConditionTemplate.objects.filter(name="Inspired").exists())

    def test_inspired_condition_is_not_behavior_altering(self) -> None:
        from world.conditions.models import ConditionTemplate

        ensure_social_combat_content()
        tpl = ConditionTemplate.objects.get(name="Inspired")
        category = tpl.category
        self.assertFalse(category.alters_behavior)

    def test_seed_creates_charm_technique(self) -> None:
        from world.magic.models.techniques import Technique

        ensure_social_combat_content()
        self.assertTrue(Technique.objects.filter(name="Charming Word").exists())

    def test_charm_technique_applies_charmed_to_enemy(self) -> None:
        from world.conditions.constants import CHARM_CONDITION_NAME
        from world.conditions.models import ConditionTemplate
        from world.magic.models.techniques import (
            ConditionTargetKind,
            TechniqueAppliedCondition,
        )

        ensure_social_combat_content()
        charmed = ConditionTemplate.objects.get(name=CHARM_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(
            condition=charmed, target_kind=ConditionTargetKind.ENEMY
        ).first()
        self.assertIsNotNone(applied, "Charm technique must apply Charmed to ENEMY")

    def test_seed_is_idempotent(self) -> None:
        from world.checks.models import CheckType

        ensure_social_combat_content()
        ensure_social_combat_content()
        self.assertEqual(CheckType.objects.filter(name="Rally").count(), 1)
