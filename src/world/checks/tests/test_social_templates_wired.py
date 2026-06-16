"""Tests verifying social ActionTemplates are wired to their ConsequencePools."""

from django.test import TestCase

from world.checks.factories import create_social_action_templates


class SocialTemplatesWiredTest(TestCase):
    def test_each_template_has_a_consequence_pool(self):
        templates = create_social_action_templates()

        for template in templates:
            self.assertIsNotNone(
                template.consequence_pool_id,
                f"Template '{template.name}' has no consequence_pool",
            )

    def test_pool_names_match_templates(self):
        templates = create_social_action_templates()

        for template in templates:
            expected_pool_name = f"Social: {template.name}"
            self.assertEqual(
                template.consequence_pool.name,
                expected_pool_name,
                f"Template '{template.name}' wired to wrong pool",
            )

    def test_idempotent(self):
        first = create_social_action_templates()
        second = create_social_action_templates()

        first_pks = {t.name: t.pk for t in first}
        second_pks = {t.name: t.pk for t in second}
        self.assertEqual(first_pks, second_pks)
