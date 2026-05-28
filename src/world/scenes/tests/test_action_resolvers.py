"""Tests for the action-key resolver registry."""

from django.test import TestCase

from world.scenes import action_resolvers


class ActionResolverRegistryTests(TestCase):
    def setUp(self) -> None:
        self._original_resolvers = action_resolvers._RESOLVER_REGISTRY.copy()

    def tearDown(self) -> None:
        action_resolvers._RESOLVER_REGISTRY.clear()
        action_resolvers._RESOLVER_REGISTRY.update(self._original_resolvers)

    def test_register_and_lookup(self) -> None:
        def my_resolver(request, outcome):
            pass

        action_resolvers.register_resolver("test_key", my_resolver)
        self.assertIs(action_resolvers.get_resolver("test_key"), my_resolver)

    def test_lookup_unknown_returns_none(self) -> None:
        self.assertIsNone(action_resolvers.get_resolver("never_registered"))

    def test_resolver_overwrites_previous(self) -> None:
        """Re-registering the same key replaces the prior resolver."""

        def first(request, outcome):
            pass

        def second(request, outcome):
            pass

        action_resolvers.register_resolver("dup_key", first)
        action_resolvers.register_resolver("dup_key", second)
        self.assertIs(action_resolvers.get_resolver("dup_key"), second)
