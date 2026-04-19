"""Phase 2/4 regression test: legacy magic.Thread family stays deleted; Phase 4
re-introduces a `Thread` class with a different shape (discriminator + typed FKs)
that REUSES the `magic_thread` table.

Phase 2 dropped the original 5-axis Thread family. Phase 4 re-adds Thread with
an entirely different schema. This test guards both: legacy classes other than
Thread itself must remain absent, and the new Thread shape must expose its
discriminator + typed FK fields.
"""

import importlib

from django.test import SimpleTestCase


class LegacyThreadFamilyDeletionTests(SimpleTestCase):
    def test_legacy_thread_classes_absent_from_module(self) -> None:
        models = importlib.import_module("world.magic.models")
        for name in (
            "ThreadType",
            "ThreadJournal",
            "ThreadResonance",
            "CharacterResonanceTotal",
        ):
            self.assertFalse(
                hasattr(models, name),
                f"{name} should have been deleted in Phase 2",
            )

    def test_new_thread_class_exists_with_discriminator_fields(self) -> None:
        from world.magic.models import Thread

        field_names = {f.name for f in Thread._meta.get_fields()}
        self.assertIn("owner", field_names)
        self.assertIn("resonance", field_names)
        self.assertIn("target_kind", field_names)
        self.assertIn("level", field_names)
        self.assertIn("developed_points", field_names)
        self.assertIn("target_trait", field_names)
        self.assertIn("target_technique", field_names)
        self.assertIn("target_object", field_names)
        self.assertIn("target_relationship_track", field_names)
        self.assertIn("target_capstone", field_names)
