"""Tests for CharacterThreadHandler.context_free_power / contextual_thread_power (#2708)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    FacetFactory,
    GiftFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.handlers import CharacterThreadHandler
from world.magic.models import LevelPowerConfig
from world.magic.services.resonance import resolve_gift_ids_by_technique
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


class GiftContextualThreadPowerTests(TestCase):
    """GIFT-thread coverage for ``contextual_thread_power`` (#2708 review Finding 2).

    None of the tests above exercise a GIFT-kind thread, which is why the
    unmemoized ``resolve_gift_ids_by_technique`` call (Finding 1) went unnoticed: a
    Major-Gift GIFT thread is minted for essentially every provisioned caster, so
    this is the common case, not an edge case.
    """

    def _gift_and_technique(self) -> tuple:
        gift = GiftFactory()
        technique = TechniqueFactory(gift=gift)
        return gift, technique

    def _gift_thread(self, sheet, gift, *, level: int = 20):
        return ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            target_trait=None,
            level=level,
        )

    def test_gift_thread_contributes_bump_when_ambiently_active(self) -> None:
        sheet = CharacterSheetFactory()
        gift, technique = self._gift_and_technique()
        # level=20 => thread_level_multiplier == 2; intensity_bump_amount=3 => scaled 6.
        thread = self._gift_thread(sheet, gift, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(technique.pk,))
        self.assertEqual(handler.contextual_thread_power(ctx), 6)

    def test_gift_thread_inactive_without_matching_technique(self) -> None:
        sheet = CharacterSheetFactory()
        gift, _technique = self._gift_and_technique()
        thread = self._gift_thread(sheet, gift, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        other_technique = TechniqueFactory()
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(other_technique.pk,))
        self.assertEqual(handler.contextual_thread_power(ctx), 0)

    def test_gift_specific_row_preferred_over_null_fallback(self) -> None:
        """A gift-specific row wins outright — it is not summed with the fallback."""
        sheet = CharacterSheetFactory()
        gift, technique = self._gift_and_technique()
        thread = self._gift_thread(sheet, gift, level=10)  # multiplier == 1
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=None,  # null-fallback row
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=100,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,  # gift-specific row — takes precedence
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=5,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(technique.pk,))
        self.assertEqual(handler.contextual_thread_power(ctx), 5)

    def test_repeated_calls_with_same_context_stay_query_free(self) -> None:
        """Regression guard for #2708 review Finding 1.

        Pre-fix, ``resolve_gift_ids_by_technique`` was not memoized, so a GIFT-owning
        character re-issued a ``Technique`` query on every single call to
        ``contextual_thread_power`` — even repeat calls with an unchanged context.
        This must now cost exactly one query, the first time.
        """
        sheet = CharacterSheetFactory()
        gift, technique = self._gift_and_technique()
        thread = self._gift_thread(sheet, gift, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext(involved_techniques=(technique.pk,))
        handler.contextual_thread_power(ctx)  # warm _all / _tier0_intensity_bumps / gift-id cache
        with self.assertNumQueries(0):
            for _ in range(5):
                handler.contextual_thread_power(ctx)

    def test_sweep_of_distinct_contexts_without_precompute_costs_one_query_per_context(
        self,
    ) -> None:
        """Documents the shape a naive per-technique sweep gets when it does NOT use
        ``gift_id_by_technique=``: the memoization cache keys on the exact
        ``involved_techniques`` tuple, so a genuinely distinct singleton per technique
        is not collapsed by the cache alone — one query per distinct context."""
        sheet = CharacterSheetFactory()
        gift, _technique = self._gift_and_technique()
        thread = self._gift_thread(sheet, gift, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        techniques = [TechniqueFactory(gift=gift) for _ in range(3)]
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps
        with self.assertNumQueries(len(techniques)):
            for t in techniques:
                handler.contextual_thread_power(PullActionContext(involved_techniques=(t.pk,)))

    def test_sweep_of_distinct_contexts_with_precomputed_gift_ids_stays_query_free(
        self,
    ) -> None:
        """The shape a batch caller (e.g. Task 5's capability oracle) should use:
        resolve the technique->gift mapping for the WHOLE technique set ONCE via
        ``resolve_gift_ids_by_technique``, then pass ``gift_id_by_technique=`` on every
        call — an N-technique sweep then costs zero additional queries, not N (#2708)."""
        sheet = CharacterSheetFactory()
        gift, _technique = self._gift_and_technique()
        thread = self._gift_thread(sheet, gift, level=20)
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        techniques = [TechniqueFactory(gift=gift) for _ in range(5)]
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps
        gift_id_by_technique = resolve_gift_ids_by_technique(tuple(t.pk for t in techniques))
        with self.assertNumQueries(0):
            for t in techniques:
                handler.contextual_thread_power(
                    PullActionContext(involved_techniques=(t.pk,)),
                    gift_id_by_technique=gift_id_by_technique,
                )

    def test_no_query_when_owned_gift_thread_has_no_bump_content(self) -> None:
        """Narrowed guard (#2708 review Finding 1): a GIFT thread with no tier-0
        INTENSITY_BUMP content at all must not trigger the ``Technique`` query, even
        when a non-GIFT thread's bump keeps ``bumps`` non-empty."""
        sheet = CharacterSheetFactory()
        gift, technique = self._gift_and_technique()
        # GIFT thread exists but authors no tier-0 INTENSITY_BUMP content.
        self._gift_thread(sheet, gift, level=20)
        # A non-GIFT thread does carry bump content, so ``bumps`` is non-empty.
        technique_thread = ThreadFactory(owner=sheet, as_technique_thread=True, level=1)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=technique_thread.resonance,
            tier=0,
            as_intensity_bump=True,
        )
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps
        ctx = PullActionContext(involved_techniques=(technique.pk,))
        with self.assertNumQueries(0):
            handler.contextual_thread_power(ctx)


class CrossGiftContextualThreadPowerTests(TestCase):
    """Cross-gift regression coverage (#2708 review CRITICAL finding — batch-precompute
    unsoundness).

    Every test in ``GiftContextualThreadPowerTests`` above uses a single shared gift for
    every technique in a sweep, which is exactly why a pre-flattened gift-id-set batch
    parameter went unnoticed as unsound: species provisioning mints a MINOR gift thread
    alongside the MAJOR one, so owning threads across two or more gifts is the normal
    shape for a finalized character, not an edge case.
    """

    def test_batch_precompute_does_not_leak_other_gift_thread_into_technique(self) -> None:
        """A gift-B thread must NOT contribute to a gift-A technique's evaluation, even
        when the caller precomputes the technique->gift mapping across the UNION of both
        techniques and passes that same mapping through on every call — the exact shape
        Task 5's docstring recommends. This is the scenario the CRITICAL finding
        describes: a pre-flattened gift-id *set* built the same way would leak gift B's
        thread into gift A's evaluation; the mapping shape must not.
        """
        sheet = CharacterSheetFactory()
        gift_a = GiftFactory()
        gift_b = GiftFactory()
        technique_a = TechniqueFactory(gift=gift_a)
        technique_b = TechniqueFactory(gift=gift_b)

        # Only gift B has an owned thread, and only it carries tier-0 bump content.
        thread_b = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift_b,
            target_trait=None,
            level=20,  # thread_level_multiplier == 2; intensity_bump_amount=3 => scaled 6.
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread_b.resonance,
            target_gift=gift_b,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps

        gift_id_by_technique = resolve_gift_ids_by_technique((technique_a.pk, technique_b.pk))

        ctx_a = PullActionContext(involved_techniques=(technique_a.pk,))
        self.assertEqual(
            handler.contextual_thread_power(ctx_a, gift_id_by_technique=gift_id_by_technique),
            0,
            "gift-B thread must not raise gift-A technique's ambient power",
        )
        ctx_b = PullActionContext(involved_techniques=(technique_b.pk,))
        self.assertEqual(
            handler.contextual_thread_power(ctx_b, gift_id_by_technique=gift_id_by_technique),
            6,
            "gift-B thread must still contribute to gift-B's own technique",
        )

    def test_batched_result_matches_unbatched_for_every_technique_in_multigift_sweep(
        self,
    ) -> None:
        """Equivalence invariant: for any input, passing ``gift_id_by_technique=`` must
        produce exactly the same decision as omitting it — the batch path is an
        optimization, never a semantic variant."""
        sheet = CharacterSheetFactory()
        gift_a = GiftFactory()
        gift_b = GiftFactory()
        techniques_a = [TechniqueFactory(gift=gift_a) for _ in range(2)]
        techniques_b = [TechniqueFactory(gift=gift_b) for _ in range(2)]

        thread_a = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift_a,
            target_trait=None,
            level=20,
        )
        thread_b = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift_b,
            target_trait=None,
            level=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread_a.resonance,
            target_gift=gift_a,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread_b.resonance,
            target_gift=gift_b,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=5,
        )
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps

        all_techniques = techniques_a + techniques_b
        gift_id_by_technique = resolve_gift_ids_by_technique(tuple(t.pk for t in all_techniques))
        for technique in all_techniques:
            ctx = PullActionContext(involved_techniques=(technique.pk,))
            unbatched = handler.contextual_thread_power(ctx)
            batched = handler.contextual_thread_power(
                ctx, gift_id_by_technique=gift_id_by_technique
            )
            self.assertEqual(
                batched, unbatched, f"batch/unbatched mismatch for technique {technique.pk}"
            )

    def test_batch_path_stays_query_free_across_multigift_ten_technique_sweep(self) -> None:
        """Query-count guarantee holds under a realistic multi-gift, 10-technique sweep:
        one query to resolve the technique->gift mapping (already spent warming the
        handler + resolving the mapping below), then zero further queries for the sweep
        itself, regardless of how many distinct gifts are represented."""
        sheet = CharacterSheetFactory()
        gift_a = GiftFactory()
        gift_b = GiftFactory()
        techniques_a = [TechniqueFactory(gift=gift_a) for _ in range(5)]
        techniques_b = [TechniqueFactory(gift=gift_b) for _ in range(5)]
        thread_a = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift_a,
            target_trait=None,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread_a.resonance,
            target_gift=gift_a,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        handler = CharacterThreadHandler(sheet.character)
        handler.contextual_thread_power(PullActionContext())  # warm _all / _tier0_intensity_bumps

        all_techniques = techniques_a + techniques_b
        gift_id_by_technique = resolve_gift_ids_by_technique(tuple(t.pk for t in all_techniques))
        with self.assertNumQueries(0):
            for technique in all_techniques:
                handler.contextual_thread_power(
                    PullActionContext(involved_techniques=(technique.pk,)),
                    gift_id_by_technique=gift_id_by_technique,
                )


class FacetIntensityBumpDivergenceTests(TestCase):
    """#2708 review Finding 3: a FACET-kind tier-0 INTENSITY_BUMP row must fail loudly
    (``logger.warning`` + skip) rather than silently under-scale — ``resolve_pull_effects``
    additionally scales a FACET pull by the worn-item quality-tier aggregate, which this
    passive path deliberately does not replicate."""

    def test_facet_row_is_skipped_and_logs_a_warning(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
        )
        effect = ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=thread.resonance,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=5,
        )
        handler = CharacterThreadHandler(sheet.character)
        with self.assertLogs("world.magic.handlers", level="WARNING") as cm:
            bumps = handler._tier0_intensity_bumps
        # Skipped, not under-scaled: the thread contributes nothing rather than a
        # value that silently disagrees with an active pull of the same thread.
        self.assertNotIn(thread.pk, bumps)
        self.assertTrue(any(str(effect.pk) in message for message in cm.output))
        self.assertTrue(any("FACET" in message for message in cm.output))

    def test_facet_row_does_not_contribute_to_contextual_thread_power(self) -> None:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=thread.resonance,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=5,
        )
        handler = CharacterThreadHandler(sheet.character)
        ctx = PullActionContext()
        with self.assertLogs("world.magic.handlers", level="WARNING"):
            self.assertEqual(handler.contextual_thread_power(ctx), 0)
