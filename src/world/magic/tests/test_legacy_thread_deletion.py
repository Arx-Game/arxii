"""Phase 2/4 regression test: legacy magic.Thread family stays deleted; Phase 4
re-introduces a `Thread` class with a different shape (discriminator + typed FKs)
that REUSES the `magic_thread` table.

Phase 2 dropped the original 5-axis Thread family. Phase 4 re-adds Thread with
an entirely different schema. This test guards both: legacy classes other than
Thread itself must remain absent, and the new Thread shape must expose its
discriminator + typed FK fields. ThreadResonance was dropped in Phase 2 and is
re-introduced by #5123 as one resonance's row inside a Thread, so it is checked
for its new shape instead of for absence.
"""

import importlib

from django.test import SimpleTestCase


class LegacyThreadFamilyDeletionTests(SimpleTestCase):
    def test_legacy_thread_classes_absent_from_module(self) -> None:
        models = importlib.import_module("world.magic.models")
        for name in (
            "ThreadType",
            "ThreadJournal",
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
        self.assertIn("target_relationship", field_names)
        self.assertIn("target_capstone", field_names)

    def test_thread_resonance_is_the_per_thread_row_not_the_legacy_class(self) -> None:
        from world.magic.models import Thread, ThreadResonance

        field_names = {f.name for f in ThreadResonance._meta.get_fields()}
        self.assertEqual(
            {"thread", "resonance", "amount", "created_at"},
            field_names & {"thread", "resonance", "amount", "created_at"},
        )
        self.assertIs(ThreadResonance._meta.get_field("thread").related_model, Thread)
