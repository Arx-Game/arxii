"""Tests for the Thread Surge ConditionTemplate seed (#2840)."""

from django.test import TestCase, override_settings

from world.conditions.constants import DurationType
from world.magic.factories import ensure_thread_surge_content


class ThreadSurgeSeedTest(TestCase):
    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_ensure_thread_surge_content_creates_template(self):
        """The factory creates a SCENE-duration, non-stackable, dispellable template."""
        template = ensure_thread_surge_content()
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "Thread Surge")
        self.assertEqual(template.default_duration_type, DurationType.SCENE)
        self.assertFalse(template.is_stackable)
        self.assertTrue(template.can_be_dispelled)

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_ensure_thread_surge_content_idempotent(self):
        """Re-running does not create a duplicate."""
        first = ensure_thread_surge_content()
        second = ensure_thread_surge_content()
        self.assertEqual(first.pk, second.pk)
