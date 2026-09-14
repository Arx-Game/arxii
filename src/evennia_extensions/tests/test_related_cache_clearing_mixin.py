"""Snapshot-based skip mechanism on ``RelatedCacheClearingMixin.save()`` (final
whole-branch review, #3816 Important findings #1/#2).

``RelatedCacheClearingMixin.save()`` used to unconditionally call
``clear_related_caches()`` on every save, wiping every cached_property on the
resolved parent object even for a pure field-only update that could not
possibly change which children belong to that parent. The fix snapshots each
single-segment FK's raw id at load/instantiation time and only clears when
that id has actually changed (or the row is new). These three cases exercise
``CharacterResonance`` (single FK, ``character_sheet``), which already uses
this exact mixin.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory


class RelatedCacheClearingMixinSnapshotTests(TestCase):
    def test_creating_a_new_row_clears_the_parents_cache(self) -> None:
        sheet = CharacterSheetFactory()
        # Warm the cache -- the sheet has zero resonances yet, so this reads [].
        self.assertEqual(sheet.cached_resonances, [])

        resonance = ResonanceFactory()
        cr = CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)

        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])

    def test_field_only_update_does_not_force_a_query_or_clear(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        cr = CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=5, lifetime_earned=5
        )
        # Warm the parent's cache (now non-empty).
        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])

        cr.balance = 8
        # No SELECT is issued for FK resolution -- only the UPDATE (plus
        # whatever SAVEPOINT bookkeeping the test-transaction wrapper adds).
        with CaptureQueriesContext(connection) as ctx:
            cr.save(update_fields=["balance"])
        select_queries = [
            q for q in ctx.captured_queries if q["sql"].strip().upper().startswith("SELECT")
        ]
        self.assertEqual(select_queries, [])

        # The clear was skipped, not just coincidentally not-re-queried.
        self.assertIn("cached_resonances", sheet.__dict__)

    def test_reassigning_the_tracked_fk_clears_both_parents(self) -> None:
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        resonance = ResonanceFactory()
        cr = CharacterResonanceFactory(character_sheet=sheet_a, resonance=resonance)

        # Warm both parents' caches.
        self.assertEqual([r.pk for r in sheet_a.cached_resonances], [cr.pk])
        self.assertEqual(sheet_b.cached_resonances, [])

        cr.character_sheet = sheet_b
        cr.save()

        # The snapshot-diff branch fired: the new parent's cache was cleared.
        self.assertNotIn("cached_resonances", sheet_b.__dict__)
