"""Tests for the identity-map-safe companion order cache (#3835)."""

from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils.functional import cached_property

from evennia_extensions.cached_property import PrunedCachedProperty
from world.combat.models import CombatEncounter


class CompanionOrderCacheTests(SimpleTestCase):
    """The current-round view must be derived from a raw all-round cache."""

    def test_raw_cache_uses_pruned_cached_property(self):
        descriptor = CombatEncounter.__dict__["companion_orders_all_cached"]
        self.assertIsInstance(descriptor, PrunedCachedProperty)
        self.assertIsInstance(descriptor, cached_property)

    def test_current_round_view_filters_identity_mapped_rows_in_python(self):
        encounter = SimpleNamespace(
            round_number=2,
            companion_orders_all_cached=[
                SimpleNamespace(round_number=1),
                SimpleNamespace(round_number=2),
                SimpleNamespace(round_number=3),
            ],
        )

        orders = CombatEncounter.companion_orders_cached.fget(encounter)

        self.assertEqual([order.round_number for order in orders], [2])

        encounter.round_number = 3
        current_round = CombatEncounter.companion_orders_cached.fget(encounter)
        self.assertEqual([order.round_number for order in current_round], [3])
