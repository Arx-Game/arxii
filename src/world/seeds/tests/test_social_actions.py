"""Production social-action seed — templates, pools, and Flirt's attraction effects (#1697)."""

from django.test import TestCase

from world.checks.constants import EffectType
from world.checks.models import ConsequenceEffect
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_actions import seed_social_action_content
from world.seeds.social_checks import seed_social_check_content
from world.seeds.social_relationships import (
    ATTRACTED_CONDITION_NAME,
    VERY_ATTRACTED_CONDITION_NAME,
    seed_social_relationship_content,
)


class SocialActionSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()

    def test_seeds_the_social_action_templates(self) -> None:
        from actions.models import ActionTemplate

        for name in ("Intimidate", "Persuade", "Deceive", "Flirt", "Perform"):
            template = ActionTemplate.objects.get(name=name)
            self.assertIsNotNone(template.consequence_pool_id, f"{name} has no pool")
        # Entrance is skipped — its "Presence" check is an unseeded placeholder (#1690).
        self.assertFalse(ActionTemplate.objects.filter(name="Entrance").exists())

    def test_flirt_success_sets_attracted_and_very_attracted(self) -> None:
        from actions.models import ActionTemplate

        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        effects = ConsequenceEffect.objects.filter(
            consequence=success, effect_type=EffectType.SET_RELATIONSHIP_CONDITION
        )
        names = set(effects.values_list("relationship_condition__name", flat=True))
        self.assertEqual(names, {ATTRACTED_CONDITION_NAME, VERY_ATTRACTED_CONDITION_NAME})
        # Attracted is permanent (no duration); Very Attracted is temporary.
        attracted = effects.get(relationship_condition__name=ATTRACTED_CONDITION_NAME)
        very = effects.get(relationship_condition__name=VERY_ATTRACTED_CONDITION_NAME)
        self.assertIsNone(attracted.relationship_condition_duration)
        self.assertIsNotNone(very.relationship_condition_duration)

    def test_flirt_does_not_apply_smitten(self) -> None:
        from actions.models import ActionTemplate

        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        self.assertFalse(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.APPLY_CONDITION
            ).exists()
        )

    def test_idempotent(self) -> None:
        seed_social_action_content()
        seed_social_action_content()
        from actions.models import ActionTemplate

        self.assertEqual(ActionTemplate.objects.filter(name="Flirt").count(), 1)
        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        # No duplicate effects on re-seed.
        self.assertEqual(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.SET_RELATIONSHIP_CONDITION
            ).count(),
            2,
        )
