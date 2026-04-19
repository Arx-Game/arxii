"""Phase 2 regression test: legacy magic.Thread family must be deleted.

Phase 4 will re-add a `Thread` class with a different shape (discriminator
+ typed FKs) that REUSES the `magic_thread` table. This test guards the
intermediate state: after Phase 2 the legacy classes must be gone, so the
Phase 4 migration can land cleanly.
"""

import importlib

from django.test import SimpleTestCase


class LegacyThreadFamilyDeletionTests(SimpleTestCase):
    def test_legacy_thread_classes_absent_from_module(self) -> None:
        models = importlib.import_module("world.magic.models")
        for name in (
            "Thread",  # legacy 5-axis Thread; Phase 4 re-adds with new shape
            "ThreadType",
            "ThreadJournal",
            "ThreadResonance",
            "CharacterResonanceTotal",
        ):
            self.assertFalse(
                hasattr(models, name),
                f"{name} should have been deleted in Phase 2",
            )
