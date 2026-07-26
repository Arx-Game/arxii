"""Query-count regression for the agency oracle's technique-power wiring (#2708).

``_technique_capability_values`` now derives real power per technique
(``technique.intensity + context_free_power + contextual_thread_power(...)``) instead
of relying on ``calculate_value()``'s bare ``technique.intensity`` fallback. Task 4's
review caught an N+1 in the technique->gift mapping ``contextual_thread_power`` needs
TWICE — once because it wasn't memoized at all, once because a batch caller resolved it
per-call instead of once for the whole sweep. This module proves the oracle's own
wiring uses the batched shape: growing the technique sweep must not add a
``Technique`` gift-lookup query per technique.

Task 5's review caught a second N+1: ``TechniqueCapabilityGrant.calculate_value()``'s
own ``CapabilityPowerConfig`` lookup (a real SELECT — ``SharedMemoryModel``'s idmapper
caches object identity, not querysets) was placed inside this sweep's per-grant loop
without being memoized the same way ``power_by_technique`` is. These tests now assert
a fixed, sweep-size-independent query count (config fetched ONCE), with AND without a
config row present — the state where the fix actually matters, since the pre-fix
double-fetch (finding 2) only bites once a row exists.
"""

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

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
from world.magic.models import CapabilityPowerConfig
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

    def test_ten_technique_sweep_costs_a_fixed_query_count_no_config_row(self) -> None:
        """No ``CapabilityPowerConfig`` row: 1 grants query + 1 gift-id-mapping query +
        1 config-existence check (fetched ONCE for the whole sweep via
        ``get_capability_power_config()``, never once per grant — Task 5 review finding
        1) = 3, regardless of sweep size."""
        sheet = self._sheet_with_technique_sweep(10)
        with self.assertNumQueries(3):
            result = _technique_capability_values(sheet)
        assert result

    def test_ten_technique_sweep_costs_a_fixed_query_count_with_config_row(self) -> None:
        """Same fixed-cost shape with a ``CapabilityPowerConfig`` row present — the
        state where the pre-fix double-fetch (Task 5 review finding 2: ``calculate_value``
        fetched once for its own inert check, ``apply_capability_curve`` fetched again
        internally) actually bit. Still exactly one config query for the whole sweep,
        threaded through every ``calculate_value(config=...)`` call."""
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        sheet = self._sheet_with_technique_sweep(10)
        with self.assertNumQueries(3):
            result = _technique_capability_values(sheet)
        assert result

    def test_gift_id_mapping_and_config_do_not_scale_with_technique_count(self) -> None:
        """Growing the sweep from 3 to 10 techniques must add ZERO queries: both the
        technique->gift mapping (Task 4 review) and the ``CapabilityPowerConfig`` fetch
        (Task 5 review) are resolved ONCE for the whole sweep, never once per grant."""
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
            large_queries,
            small_queries,
            f"expected the SAME query count (O(1), not O(N)) growing from 3 to 10 "
            f"techniques; got {small_queries} -> {large_queries}. An extra query per "
            f"technique here means the gift mapping or the config lookup is being "
            f"re-resolved per grant instead of once for the whole sweep.",
        )
