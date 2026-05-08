"""Tests for the action-key resolver + menu-contributor registry."""

from django.test import TestCase

from world.scenes import action_resolvers


class ActionResolverRegistryTests(TestCase):
    def setUp(self) -> None:
        self._original_resolvers = action_resolvers._RESOLVER_REGISTRY.copy()
        self._original_contributors = list(action_resolvers._MENU_CONTRIBUTORS)

    def tearDown(self) -> None:
        action_resolvers._RESOLVER_REGISTRY.clear()
        action_resolvers._RESOLVER_REGISTRY.update(self._original_resolvers)
        action_resolvers._MENU_CONTRIBUTORS.clear()
        action_resolvers._MENU_CONTRIBUTORS.extend(self._original_contributors)

    def test_register_and_lookup(self) -> None:
        def my_resolver(request, outcome):
            pass

        action_resolvers.register_resolver("test_key", my_resolver)
        self.assertIs(action_resolvers.get_resolver("test_key"), my_resolver)

    def test_lookup_unknown_returns_none(self) -> None:
        self.assertIsNone(action_resolvers.get_resolver("never_registered"))

    def test_register_menu_contributor(self) -> None:
        def contributor(character, scene):
            return []

        action_resolvers.register_menu_contributor(contributor)
        self.assertIn(contributor, action_resolvers.get_menu_contributors())

    def test_menu_contributor_idempotent(self) -> None:
        def c(character, scene):
            return []

        action_resolvers.register_menu_contributor(c)
        action_resolvers.register_menu_contributor(c)
        self.assertEqual(action_resolvers.get_menu_contributors().count(c), 1)

    def test_get_menu_contributors_returns_copy(self) -> None:
        """Mutating the returned list does not affect the registry."""

        def contrib(character, scene):
            return []

        action_resolvers.register_menu_contributor(contrib)
        returned = action_resolvers.get_menu_contributors()
        returned.clear()
        self.assertIn(contrib, action_resolvers.get_menu_contributors())

    def test_resolver_overwrites_previous(self) -> None:
        """Re-registering the same key replaces the prior resolver."""

        def first(request, outcome):
            pass

        def second(request, outcome):
            pass

        action_resolvers.register_resolver("dup_key", first)
        action_resolvers.register_resolver("dup_key", second)
        self.assertIs(action_resolvers.get_resolver("dup_key"), second)
