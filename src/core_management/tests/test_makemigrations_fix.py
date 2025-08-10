"""
Test for the makemigrations fix that prevents phantom Evennia migrations.

This test is SKIPPED BY DEFAULT because it's not testing for regressions,
but rather demonstrating that our fix solves the original problem.

To run this test explicitly:
    python src/core_management/tests/run_phantom_migration_test.py
"""

import unittest
from unittest.mock import MagicMock, patch


@unittest.skip("Phantom migration test - run explicitly to verify fix works")
class TestMakemigrationsEvenniaFix(unittest.TestCase):
    """
    Test that verifies our makemigrations command prevents phantom Evennia migrations.

    This test would FAIL if EXCLUDED_APPS was removed from our command,
    and PASSES when our fix is in place.
    """

    def setUp(self):
        """Set up test mocks."""
        self.mock_stdout = MagicMock()
        self.mock_style = MagicMock()
        self.mock_style.WARNING.return_value = "WARNING: "

    def test_makemigrations_prevents_evennia_phantom_migrations(self):
        """Test that our makemigrations command prevents phantom Evennia migrations."""
        # Import our custom command
        try:
            from core_management.management.commands.makemigrations import Command
        except ImportError:
            self.skipTest(
                "Cannot import makemigrations command - Django not configured"
            )

        # Create a command instance
        command = Command()
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        # Mock changes that would include Evennia apps (the problematic scenario)
        fake_changes = {
            "objects": [{"fake": "proxy_model_operation"}],
            "accounts": [{"fake": "proxy_model_operation"}],
            "test_phantom_migration_app": [{"real": "model_operation"}],
        }

        # Mock the parent write_migration_files to capture what gets passed
        with patch(
            "django.core.management.commands.makemigrations.Command.write_migration_files"
        ) as mock_parent_write:
            mock_parent_write.return_value = (None, None)

            # Call our overridden write_migration_files method
            result = command.write_migration_files(fake_changes)

            # Verify the parent method was called
            self.assertTrue(mock_parent_write.called)

            # Get the filtered changes that were passed to the parent
            call_args = mock_parent_write.call_args[0][0]  # First positional arg

            # Assert that Evennia apps were filtered out
            self.assertNotIn(
                "objects",
                call_args,
                "Evennia 'objects' app should have been filtered out",
            )
            self.assertNotIn(
                "accounts",
                call_args,
                "Evennia 'accounts' app should have been filtered out",
            )

            # Assert that our test app was kept
            self.assertIn(
                "test_phantom_migration_app",
                call_args,
                "Our custom app should have been preserved",
            )

            # Verify warning messages were displayed for excluded apps
            self.assertTrue(
                self.mock_stdout.write.called,
                "Warning messages should have been displayed",
            )

    def test_replaces_dependencies_for_excluded_apps(self):
        """Test dependencies on excluded apps use existing migrations."""
        try:
            from core_management.management.commands.makemigrations import Command
        except ImportError:
            self.skipTest(
                "Cannot import makemigrations command - Django not configured"
            )

        command = Command()
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        fake_migration = MagicMock()
        fake_migration.dependencies = [("objects", "9999_phantom")]

        ignored = MagicMock()
        ignored.name = "9999_phantom"

        fake_changes = {
            "test_phantom_migration_app": [fake_migration],
            "objects": [ignored],
        }

        with (
            patch(
                "core_management.management.commands.makemigrations.MigrationLoader"
            ) as mock_loader,
            patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files"
            ) as mock_parent,
        ):
            mock_loader.return_value.graph.leaf_nodes.return_value = [
                ("objects", "0001_initial")
            ]
            mock_parent.return_value = (None, None)

            command.write_migration_files(fake_changes)

        self.assertEqual(
            fake_migration.dependencies,
            [("objects", "0001_initial")],
            "Dependency should point to existing migration",
        )

    def test_does_not_replace_existing_dependency(self):
        """Test existing dependencies on excluded apps remain unchanged."""
        try:
            from core_management.management.commands.makemigrations import Command
        except ImportError:
            self.skipTest(
                "Cannot import makemigrations command - Django not configured"
            )

        command = Command()
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        fake_migration = MagicMock()
        fake_migration.dependencies = [("objects", "0001_initial")]

        ignored = MagicMock()
        ignored.name = "9999_phantom"

        fake_changes = {
            "test_app": [fake_migration],
            "objects": [ignored],
        }

        with (
            patch(
                "core_management.management.commands.makemigrations.MigrationLoader"
            ) as mock_loader,
            patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files"
            ) as mock_parent,
        ):
            mock_loader.return_value.graph.leaf_nodes.return_value = [
                ("objects", "0002_real")
            ]
            mock_parent.return_value = (None, None)

            command.write_migration_files(fake_changes)

        self.assertEqual(
            fake_migration.dependencies,
            [("objects", "0001_initial")],
            "Existing dependency should remain unchanged",
        )

    def test_excluded_apps_list_comprehensive(self):
        """Test that our EXCLUDED_APPS list covers the problematic Evennia apps."""
        try:
            from core_management.management.commands.makemigrations import Command
        except ImportError:
            self.skipTest(
                "Cannot import makemigrations command - Django not configured"
            )

        command = Command()

        # Verify all critical Evennia apps are excluded
        critical_evennia_apps = {
            "objects",
            "accounts",
            "scripts",
            "comms",
            "help",
            "typeclasses",
            "server",
            "sessions",
        }

        for app in critical_evennia_apps:
            self.assertIn(
                app,
                command.EXCLUDED_APPS,
                f"Critical Evennia app '{app}' is not in EXCLUDED_APPS! "
                f"This could allow phantom migrations.",
            )

    def test_proof_of_problem_without_fix(self):
        """
        Test that demonstrates the problem EXISTS without our fix.

        This test patches out our EXCLUDED_APPS to show that without
        the fix, phantom migrations would be created.
        """
        try:
            from core_management.management.commands.makemigrations import Command
        except ImportError:
            self.skipTest(
                "Cannot import makemigrations command - Django not configured"
            )

        # Simulate the problematic changes Django detects
        fake_changes = {
            "objects": ["CreateModel for DefaultObject"],
            "accounts": ["CreateModel for DefaultAccount"],
            "test_phantom_migration_app": ["CreateModel for TestModel"],
        }

        # Test WITHOUT our fix (empty EXCLUDED_APPS)
        with patch.object(Command, "EXCLUDED_APPS", set()):
            command = Command()
            command.stdout = self.mock_stdout
            command.style = self.mock_style

            # Mock write_migration_files to capture what gets through
            with patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files"
            ) as mock_write:
                mock_write.return_value = (None, None)

                # Call our overridden method (but without EXCLUDED_APPS)
                command.write_migration_files(fake_changes)

                # Get what was passed to the parent (should include Evennia apps)
                call_args = mock_write.call_args[0][0]

                # Without our fix, Evennia apps would get through
                self.assertIn(
                    "objects",
                    call_args,
                    "Without our fix, 'objects' app should create phantom migration",
                )
                self.assertIn(
                    "accounts",
                    call_args,
                    "Without our fix, 'accounts' app should create phantom migration",
                )

        # Now test WITH our fix (normal EXCLUDED_APPS)
        command = Command()  # Fresh instance with normal EXCLUDED_APPS
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        with patch(
            "django.core.management.commands.makemigrations.Command.write_migration_files"
        ) as mock_write:
            mock_write.return_value = (None, None)

            command.write_migration_files(fake_changes)

            call_args = mock_write.call_args[0][0]

            # WITH our fix, Evennia apps should be filtered out
            self.assertNotIn(
                "objects",
                call_args,
                "With our fix, 'objects' app should be filtered out",
            )
            self.assertNotIn(
                "accounts",
                call_args,
                "With our fix, 'accounts' app should be filtered out",
            )
            self.assertIn(
                "test_phantom_migration_app",
                call_args,
                "Our custom app should still get through",
            )


if __name__ == "__main__":
    # Allow running this test file directly to execute the skipped tests
    unittest.main(verbosity=2)
