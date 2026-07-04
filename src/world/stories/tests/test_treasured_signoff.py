from django.test import TestCase
from django.utils import timezone

from world.boundaries.factories import ContentThemeFactory
from world.stories.factories import StakeTemplateFactory, TreasuredSignoffFactory


class TreasuredSignoffModelTests(TestCase):
    def test_signoff_active_then_withdrawn(self):
        so = TreasuredSignoffFactory()
        self.assertTrue(so.active)
        so.withdrawn_at = timezone.now()
        self.assertFalse(so.active)


class StakeTemplateContentThemesTests(TestCase):
    def test_template_carries_content_themes(self):
        template = StakeTemplateFactory()
        theme = ContentThemeFactory()
        template.content_themes.add(theme)
        self.assertIn(theme, template.content_themes.all())
