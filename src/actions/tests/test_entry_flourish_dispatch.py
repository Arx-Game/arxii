from django.test import TestCase


class ActionTemplateEntryFlourishFieldTest(TestCase):
    def test_entrance_template_grants_entry_flourish(self):
        from world.checks.factories import create_social_action_templates

        templates = create_social_action_templates()
        entrance = next(t for t in templates if t.name == "Entrance")
        self.assertTrue(entrance.grants_entry_flourish)

    def test_other_social_templates_do_not_grant_flourish(self):
        from world.checks.factories import create_social_action_templates

        templates = create_social_action_templates()
        for t in templates:
            if t.name != "Entrance":
                self.assertFalse(t.grants_entry_flourish, f"{t.name} should not grant flourish")

    def test_field_defaults_false(self):
        from actions.factories import ActionTemplateFactory

        template = ActionTemplateFactory()
        self.assertFalse(template.grants_entry_flourish)
