"""ActionTemplate cost + pose fields (#745 — Spread a Tale Phase 1a, Task 1)."""

from django.test import TestCase

from actions.factories import ActionTemplateFactory


class ActionTemplateCostFieldsTest(TestCase):
    def test_defaults_are_free_and_no_pose(self) -> None:
        template = ActionTemplateFactory()
        self.assertFalse(template.accepts_pose_text)
        self.assertEqual(template.ap_cost, 0)
        self.assertEqual(template.social_fatigue_cost, 0)

    def test_fields_settable(self) -> None:
        template = ActionTemplateFactory(accepts_pose_text=True, ap_cost=20, social_fatigue_cost=5)
        self.assertTrue(template.accepts_pose_text)
        self.assertEqual(template.ap_cost, 20)
        self.assertEqual(template.social_fatigue_cost, 5)


class ActionTemplateConsentCategoryTest(TestCase):
    def test_consent_category_optional_and_settable(self):
        from world.consent.factories import SocialConsentCategoryFactory

        cat = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        tmpl = ActionTemplateFactory(consent_category=cat)
        self.assertEqual(tmpl.consent_category.key, "romantic")
        self.assertIsNone(ActionTemplateFactory().consent_category)
