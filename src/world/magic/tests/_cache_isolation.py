"""Reusable test mixin for resonance-environment manager cache isolation.

The ``AffinityInteractionManager`` and ``ResonanceAlignmentBoonTierManager``
use process-lived class-level caches (survive DB rollback). Any test that
exercises the resonance-environment primitive or its manager accessors must
clear these caches in ``setUp``; otherwise stale or negative-cached entries
from a prior test class can corrupt subsequent tests in a non-deterministic,
order-dependent way.

Usage
-----
Mix ``ResonanceCacheIsolationMixin`` into any ``TestCase`` subclass that
creates ``AffinityInteraction`` or ``ResonanceAlignmentBoonTier`` rows, or
calls ``evaluate_resonance_environment``::

    from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin

    class MyTest(ResonanceCacheIsolationMixin, TestCase):
        ...

This mixin's ``setUp`` runs as part of the cooperative ``super().setUp()``
chain. If a subclass defines its own ``setUp``, it MUST call
``super().setUp()`` and create any cache-sensitive test data (rows the
manager caches will read) AFTER that ``super().setUp()`` call returns —
otherwise data created before ``super().setUp()`` is cached before the
clear and the cache will be stale.

T6, T7, T15 tasks must import and apply this mixin to their test classes.
"""

from __future__ import annotations

from world.magic.models.resonance_environment import (
    AffinityInteraction,
    ResonanceAlignmentBoonTier,
)


class ResonanceCacheIsolationMixin:
    """Mixin that clears resonance-environment manager caches before each test.

    Apply to any TestCase that touches AffinityInteraction rows, calls
    interaction_for(), boon_condition_templates(), or exercises
    evaluate_resonance_environment().
    """

    def setUp(self) -> None:
        AffinityInteraction.objects.clear_cache()
        ResonanceAlignmentBoonTier.objects.clear_cache()
        super().setUp()  # type: ignore[misc]
