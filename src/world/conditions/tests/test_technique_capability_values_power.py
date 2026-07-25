"""Query-count regression for the agency oracle's technique-power wiring (#2708).

``_technique_capability_values`` now derives real power per technique
(``technique.intensity + context_free_power + contextual_thread_power(...)``) instead
of relying on ``calculate_value()``'s bare ``technique.intensity`` fallback. Task 4's
review caught an N+1 in the technique->gift mapping ``contextual_thread_power`` needs
TWICE — once because it wasn't memoized at all, once because a batch caller resolved it
per-call instead of once for the whole sweep. This module proves the oracle's own
wiring uses the batched shape: growing the technique sweep must not add a
``Technique`` gift-lookup query per technique.
"""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.services import _technique_capability_values
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.types.pull import PullActionContext


class TechniqueCapabilityValuesQueryCountTests(TestCase):
    """A GIFT thread with tier-0 ambient bump content is the shape that makes
    ``contextual_thread_power`` need the technique->gift mapping at all — without one,
    the mapping resolution is skipped entirely and this test would prove nothing."""

    def _sheet_with_technique_sweep(self, technique_count: int) -> CharacterSheet:
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        capability = CapabilityTypeFactory(name=f"sweep_cap_{technique_count}")
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            target_trait=None,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        for _ in range(technique_count):
            technique = TechniqueFactory(gift=gift, intensity=1)
            TechniqueCapabilityGrantFactory(
                technique=technique,
                capability=capability,
                base_value=1,
                intensity_multiplier=Decimal(0),
            )
            CharacterTechniqueFactory(character=sheet, technique=technique)
        # Warm the handler's context_free_power / _all / _tier0_intensity_bumps caches
        # the way an earlier read in the same request already would have.
        handler = sheet.character.threads
        _ = handler.context_free_power
        handler.contextual_thread_power(PullActionContext())
        return sheet

    def test_ten_technique_sweep_costs_a_fixed_query_count(self) -> None:
        """1 grants query + 1 gift-id-mapping query + 10 per-grant
        ``CapabilityPowerConfig`` checks (Task 1, orthogonal to this fix) = 12. If the
        technique->gift mapping were re-resolved per technique instead of once for the
        whole sweep (the N+1 Task 4's review caught twice), this would be 22, not 12."""
        sheet = self._sheet_with_technique_sweep(10)
        with self.assertNumQueries(12):
            result = _technique_capability_values(sheet)
        assert result

    def test_gift_id_mapping_does_not_scale_with_technique_count(self) -> None:
        """Growing the sweep from 3 to 10 techniques must add exactly 7 queries — one
        per added grant's own ``CapabilityPowerConfig`` check (pre-existing, Task 1,
        orthogonal to this fix) — and NOT an eighth-or-more query per technique from a
        re-resolved ``Technique`` gift lookup (the N+1 Task 4's review caught twice)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        small_sheet = self._sheet_with_technique_sweep(3)
        large_sheet = self._sheet_with_technique_sweep(10)

        with CaptureQueriesContext(connection) as small_ctx:
            small_result = _technique_capability_values(small_sheet)
        with CaptureQueriesContext(connection) as large_ctx:
            large_result = _technique_capability_values(large_sheet)

        assert small_result
        assert large_result

        small_queries = len(small_ctx.captured_queries)
        large_queries = len(large_ctx.captured_queries)
        self.assertEqual(
            large_queries - small_queries,
            7,
            f"expected exactly +7 queries (10-3 grants' own config checks) growing "
            f"from 3 to 10 techniques; got {small_queries} -> {large_queries}. An "
            f"extra query per technique here means the technique->gift mapping is "
            f"being re-resolved per call instead of once for the whole sweep.",
        )
