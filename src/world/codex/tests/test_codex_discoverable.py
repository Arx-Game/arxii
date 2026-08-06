"""Tests that CodexEntry inherits DiscoverableContent (nullable discovery_achievement)."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory


class CodexEntryDiscoverableTests(TestCase):
    """CodexEntry must carry a nullable discovery_achievement FK from DiscoverableContent."""

    def test_codex_entry_has_nullable_discovery_achievement(self):
        entry = CodexEntryFactory()
        self.assertIsNone(entry.discovery_achievement)
