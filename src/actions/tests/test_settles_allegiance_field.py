"""ActionTemplate.settles_allegiance validation (#4091)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ActionTemplateFactory, ConsequencePoolFactory


class SettlesAllegianceTests(TestCase):
    def test_default_false(self):
        self.assertFalse(ActionTemplateFactory().settles_allegiance)

    def test_only_one_settle_template(self):
        ActionTemplateFactory(name="Settle A", category="social", settles_allegiance=True)
        second = ActionTemplateFactory(name="Settle B", category="social", settles_allegiance=True)
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_settle_template_has_no_pool(self):
        template = ActionTemplateFactory(
            name="Settle C",
            category="social",
            settles_allegiance=True,
            consequence_pool=ConsequencePoolFactory(),
        )
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_settle_template_is_social(self):
        template = ActionTemplateFactory(name="Settle D", category="test", settles_allegiance=True)
        with self.assertRaises(ValidationError):
            template.full_clean()
