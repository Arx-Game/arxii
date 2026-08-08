"""#3066: check-based development points accrue through the real social-action
resolution path (``respond_to_action_request`` -> ``_resolve_action_against_persona``
-> ``start_action_resolution`` -> ``perform_check``), not just when ``perform_check``
is called directly.

Before #3066, ``_resolve_action_against_persona`` folded ``EFFORT_CHECK_MODIFIER``
into ``extra_modifiers`` itself and always called ``perform_check`` with
``effort_level=None`` -- so a real social action's declared effort shifted the
roll but never awarded check-based development points, exactly the #3048 audit's
criticism (green suite, dead feature) applied to the scene-action production path.
"""

from unittest.mock import patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.fatigue.constants import EffortLevel
from world.progression.models import DevelopmentPoints, WeeklySkillUsage
from world.progression.services.skill_development import calculate_check_dev_points
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


class SocialActionDevelopmentAwardTests(TestCase):
    """A plain (non-technique) social action, resolved through the real production
    entry point, must award WeeklySkillUsage + DevelopmentPoints rows for the
    initiator when they declare an effort level."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        cls.trait, _ = Trait.objects.get_or_create(
            name="social_dp_test_charm",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.SOCIAL},
        )
        cls.category = CheckCategoryFactory(name="social_dp_test_category")
        cls.check_type = CheckTypeFactory(name="social_dp_test_check", category=cls.category)
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.trait, weight=1)
        cls.action_template = ActionTemplateFactory(check_type=cls.check_type)
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        WeeklySkillUsage.flush_instance_cache()
        DevelopmentPoints.flush_instance_cache()
        ResultChart.clear_cache()
        WeeklySkillUsage.objects.filter(character_sheet=self.initiator.character_sheet).delete()
        DevelopmentPoints.objects.filter(character_sheet=self.initiator.character_sheet).delete()
        CharacterTraitValue.objects.create(
            character=self.initiator.character_sheet, trait=self.trait, value=30
        )
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def _make_request(self, effort_level: str):
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="social_dp_test_action",
            effort_level=effort_level,
            status=ActionRequestStatus.PENDING,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])
        return request

    def test_plain_social_action_awards_development_points(self):
        request = self._make_request(EffortLevel.HIGH)

        result = respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        self.assertIsNotNone(result)
        expected_dp = calculate_check_dev_points(EffortLevel.HIGH, path_level=1)
        self.assertGreater(expected_dp, 0)

        usage = WeeklySkillUsage.objects.get(
            character_sheet=self.initiator.character_sheet, trait=self.trait
        )
        self.assertEqual(usage.check_count, 1)
        self.assertEqual(usage.points_earned, expected_dp)

        dev = DevelopmentPoints.objects.get(
            character_sheet=self.initiator.character_sheet, trait=self.trait
        )
        self.assertEqual(dev.total_earned, expected_dp)
