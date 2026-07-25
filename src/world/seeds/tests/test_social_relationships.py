"""Social-relationship seed — allure target + Attracted To / Very Attracted conditions (#1697)."""

from django.test import TestCase, override_settings

from world.mechanics.models import ModifierTarget
from world.relationships.models import RelationshipCondition
from world.seeds.social_relationships import (
    ALLURE_TARGET_NAME,
    ATTRACTED_CONDITION_NAME,
    VERY_ATTRACTED_CONDITION_NAME,
    seed_social_relationship_content,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class SocialRelationshipSeedTests(TestCase):
    """mechanics.ModifierCategory/ModifierTarget are content-repo-owned (#2698);
    ensure_allure_target() only invents them under SEED_SAMPLE_CONTENT — this
    test asserts on the real allure target, so it opts in."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_social_relationship_content()

    def test_seeds_allure_target(self) -> None:
        self.assertTrue(ModifierTarget.objects.filter(name=ALLURE_TARGET_NAME).exists())

    def test_conditions_gate_allure(self) -> None:
        allure = ModifierTarget.objects.get(name=ALLURE_TARGET_NAME)
        for name in (ATTRACTED_CONDITION_NAME, VERY_ATTRACTED_CONDITION_NAME):
            condition = RelationshipCondition.objects.get(name=name)
            self.assertIn(allure, list(condition.gates_modifiers.all()))

    def test_idempotent(self) -> None:
        seed_social_relationship_content()
        seed_social_relationship_content()
        self.assertEqual(ModifierTarget.objects.filter(name=ALLURE_TARGET_NAME).count(), 1)
        self.assertEqual(
            RelationshipCondition.objects.filter(name=ATTRACTED_CONDITION_NAME).count(), 1
        )
