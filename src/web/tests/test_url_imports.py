"""
Tests to ensure URL loading doesn't trigger problematic import cascades.

This test suite guards against import chains that cause failures when
loading Django URL patterns. Specifically, it prevents regressions where
API views import typeclasses that trigger Evennia command imports.

The problematic import chain was:
    views.py → typeclasses.characters → commands.utils → commands.__init__
    → commands.evennia_overrides.builder → evennia.commands.default.building
    → evennia.prototypes.menus → evennia.utils.evmenu (which had a bug)

The fix uses TYPE_CHECKING guards in views and removes module-level
command imports from __init__.py files.
"""

import sys
from unittest.mock import patch

from django.test import SimpleTestCase


class URLImportTests(SimpleTestCase):
    """Test that URL loading doesn't trigger problematic imports."""

    def test_url_loading_does_not_import_evennia_building_commands(self):
        """
        Ensure loading web.urls doesn't trigger evennia.commands.default.building import.

        This import chain caused failures due to a bug in evennia.utils.evmenu.
        The fix uses TYPE_CHECKING guards in views and removes module-level
        imports from commands/__init__.py files.
        """
        # Track which modules get imported
        imported_modules_before = set(sys.modules.keys())

        # Clear any cached URL modules to force fresh import
        modules_to_clear = [
            "web.urls",
            "world.goals.urls",
            "world.goals.views",
            "world.conditions.urls",
            "world.conditions.views",
        ]
        for mod in modules_to_clear:
            sys.modules.pop(mod, None)

        # Patch the problematic import to track if it's attempted
        with patch.dict(sys.modules, {"evennia.commands.default.building": None}):
            # Import the URL module - should not trigger building import
            from django.urls import get_resolver

            resolver = get_resolver()

            # Verify we got some URL patterns loaded
            self.assertGreater(len(resolver.url_patterns), 0)

        # Check that building commands weren't imported during URL loading
        imported_modules_after = set(sys.modules.keys())
        new_imports = imported_modules_after - imported_modules_before

        # These modules should NOT be imported during URL loading
        problematic_imports = [
            "evennia.commands.default.building",
            "evennia.prototypes.menus",
            "evennia.utils.evmenu",
        ]

        for module in problematic_imports:
            self.assertNotIn(
                module,
                new_imports,
                f"URL loading should not trigger import of {module}. "
                f"This likely means a view or model is importing from "
                f"typeclasses.characters or commands at module level.",
            )

    def test_goals_urls_load_without_character_import(self):
        """Ensure goals.urls can be imported without triggering Character import."""
        # Clear cached modules
        sys.modules.pop("world.goals.urls", None)
        sys.modules.pop("world.goals.views", None)

        # Track imports
        imported_before = set(sys.modules.keys())

        # Import goals URLs
        import world.goals.urls  # noqa: F401

        imported_after = set(sys.modules.keys())
        new_imports = imported_after - imported_before

        # typeclasses.characters should NOT be imported at module level
        # (it should be in TYPE_CHECKING block)
        self.assertNotIn(
            "typeclasses.characters",
            new_imports,
            "goals.views should use TYPE_CHECKING for Character import",
        )

    def test_conditions_urls_load_without_character_import(self):
        """Ensure conditions.urls can be imported without triggering Character import."""
        # Clear cached modules
        sys.modules.pop("world.conditions.urls", None)
        sys.modules.pop("world.conditions.views", None)

        # Track imports
        imported_before = set(sys.modules.keys())

        # Import conditions URLs
        import world.conditions.urls  # noqa: F401

        imported_after = set(sys.modules.keys())
        new_imports = imported_after - imported_before

        # typeclasses.characters should NOT be imported at module level
        self.assertNotIn(
            "typeclasses.characters",
            new_imports,
            "conditions.views should use TYPE_CHECKING for Character import",
        )

    def test_commands_init_does_not_import_command_classes(self):
        """Ensure commands/__init__.py doesn't import command classes."""
        # Clear cached module
        sys.modules.pop("commands", None)

        # Track imports
        imported_before = set(sys.modules.keys())

        # Import commands package
        import commands  # noqa: F401

        imported_after = set(sys.modules.keys())
        new_imports = imported_after - imported_before

        # These should NOT be imported by commands/__init__.py
        should_not_import = [
            "commands.door",
            "commands.evennia_overrides.communication",
            "commands.evennia_overrides.movement",
            "commands.evennia_overrides.perception",
            "commands.evennia_overrides.builder",
        ]

        for module in should_not_import:
            self.assertNotIn(
                module,
                new_imports,
                f"commands/__init__.py should not import {module}. "
                f"Command classes should be imported from specific modules.",
            )

    def test_shared_character_context_mixin_exists(self):
        """Ensure CharacterContextMixin is centralized in web.api.mixins."""
        from web.api.mixins import CharacterContextMixin

        # Verify the mixin has the expected method
        self.assertTrue(hasattr(CharacterContextMixin, "_get_character"))

    def test_goals_views_uses_shared_mixin(self):
        """Ensure goals views use the shared CharacterContextMixin."""
        from web.api.mixins import CharacterContextMixin
        from world.goals.views import CharacterGoalViewSet, GoalJournalViewSet

        # Both viewsets should inherit from the shared mixin
        self.assertTrue(issubclass(CharacterGoalViewSet, CharacterContextMixin))
        self.assertTrue(issubclass(GoalJournalViewSet, CharacterContextMixin))

    def test_conditions_views_uses_shared_mixin(self):
        """Ensure conditions views use the shared CharacterContextMixin."""
        from web.api.mixins import CharacterContextMixin
        from world.conditions.views import CharacterConditionsViewSet

        # ViewSet should inherit from the shared mixin
        self.assertTrue(issubclass(CharacterConditionsViewSet, CharacterContextMixin))
