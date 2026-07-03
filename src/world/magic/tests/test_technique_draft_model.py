"""Tests for the TechniqueDraft model and its payload children."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models import TechniqueDraft


class TechniqueDraftModelTests(TestCase):
    """Model-level tests for TechniqueDraft."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_one_draft_per_character(self) -> None:
        """OneToOneField enforces exactly one draft per CharacterSheet."""
        TechniqueDraft.objects.create(character=self.sheet, name="A")
        with self.assertRaises(IntegrityError):
            TechniqueDraft.objects.create(character=self.sheet, name="B")

    def test_consequence_pool_field_defaults_null(self) -> None:
        draft = TechniqueDraft.objects.create(character=self.sheet, name="A")
        self.assertIsNone(draft.consequence_pool_id)

    def test_consequence_pool_nulls_out_on_pool_delete(self) -> None:
        from actions.factories import ConsequencePoolFactory

        pool = ConsequencePoolFactory()
        draft = TechniqueDraft.objects.create(character=self.sheet, name="A", consequence_pool=pool)
        pool.delete()
        # The Collector-driven bulk SET_NULL bypasses the idmapper identity map, so
        # even refresh_from_db() would return the stale cached instance without this
        # flush (see sharedmemory-model skill's stale-cache-traps reference).
        TechniqueDraft.flush_instance_cache()
        draft.refresh_from_db()
        self.assertIsNone(draft.consequence_pool_id)
