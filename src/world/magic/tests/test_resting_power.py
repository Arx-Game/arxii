"""Tests for CharacterThreadHandler.context_free_power / contextual_thread_power (#2708)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.constants import TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.handlers import CharacterThreadHandler
from world.magic.models import LevelPowerConfig
from world.magic.types.pull import PullActionContext


class ContextFreePowerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_zero_without_any_power_config(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        self.assertEqual(handler.context_free_power, 0)

    def test_includes_character_level_term(self) -> None:
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=2, technique_level_bonus=0)
        CharacterClassLevelFactory(character=self.sheet, level=4)
        handler = CharacterThreadHandler(self.sheet.character)
        self.assertEqual(handler.context_free_power, 8)

    def test_is_memoized(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        _ = handler.context_free_power  # warm the cache
        with self.assertNumQueries(0):
            self.assertEqual(handler.context_free_power, handler.context_free_power)

    def test_invalidate_clears_it(self) -> None:
        handler = CharacterThreadHandler(self.sheet.character)
        _ = handler.context_free_power  # warm the cache
        handler.invalidate()
        self.assertNotIn("context_free_power", handler.__dict__)


class ContextualThreadPowerTests(TestCase):
    def _technique_thread(self, sheet, *, level=0):
        return ThreadFactory(owner=sheet, as_technique_thread=True, level=level)

    def test_zero_without_threads(self) -> None:
        sheet = CharacterSheetFactory()
        handler = CharacterThreadHandler(sheet.character)
        self.assertEqual(handler.contextual_thread_power(PullActionContext()), 0)

    def test_ambiently_inactive_thread_contributes_nothing(self) -> None:
        sheet = CharacterSheetFactory()
        thread = self._technique_thread(sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=thread.resonance,
            tier=0,
            as_intensity_bump=True,
        )
        handler = CharacterThreadHandler(sheet.character)
        # No involved_techniques => _anchor_ambiently_active's TECHNIQUE arm is False.
        self.assertEqual(handler.contextual_thread_power(PullActionContext()), 0)

    def test_ambiently_active_thread_contributes_its_tier0_bump(self) -> None:
        sheet = CharacterSheetFactory()
        # level=20 => thread_level_multiplier == 2; intensity_bump_amount=3 => scaled 6.
        thread = self._technique_thread(sheet, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=thread.resonance,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(thread.target_technique_id,))
        self.assertEqual(handler.contextual_thread_power(ctx), 6)

    def test_min_thread_level_gate_excludes_underleveled_thread(self) -> None:
        sheet = CharacterSheetFactory()
        thread = self._technique_thread(sheet, level=1)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=thread.resonance,
            tier=0,
            min_thread_level=5,
            as_intensity_bump=True,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(thread.target_technique_id,))
        self.assertEqual(handler.contextual_thread_power(ctx), 0)

    def test_tier0_rows_batched_in_one_query(self) -> None:
        """Sweeping many contexts must not re-query per context."""
        sheet = CharacterSheetFactory()
        thread = self._technique_thread(sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=thread.resonance,
            tier=0,
            as_intensity_bump=True,
        )
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm
        with self.assertNumQueries(0):
            for _ in range(5):
                handler.contextual_thread_power(PullActionContext())

    def test_query_count_does_not_scale_with_thread_count(self) -> None:
        """A character with several owned threads still warms in a bounded number of
        queries, and repeated sweeps thereafter stay query-free (#2708)."""
        sheet = CharacterSheetFactory()
        threads = []
        for _ in range(6):
            thread = self._technique_thread(sheet)
            ThreadPullEffectFactory(
                target_kind=TargetKind.TECHNIQUE,
                resonance=thread.resonance,
                tier=0,
                as_intensity_bump=True,
            )
            threads.append(thread)
        handler = CharacterThreadHandler(sheet.character)
        # Warm-up costs exactly 2 queries regardless of thread count: one for ``_all``,
        # one OR'd query fetching every tier-0 INTENSITY_BUMP row across all 6 threads'
        # (target_kind, resonance) keys at once (each thread has its own resonance here,
        # proving the batch isn't relying on threads sharing a key).
        with self.assertNumQueries(2):
            handler.contextual_thread_power(PullActionContext())
        with self.assertNumQueries(0):
            for _ in range(3):
                handler.contextual_thread_power(PullActionContext())
