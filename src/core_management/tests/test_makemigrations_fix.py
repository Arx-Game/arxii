"""Unit tests for the phantom-Evennia-migration filter in our makemigrations.

These exercise ``Command.write_migration_files`` directly. That is useful but
**narrow**, and the narrowness had teeth: because they import the class rather
than ask Django which class it runs, they passed happily for the entire period
(#2885) when Django was running ``django_linear_migrations``' command instead
and this filter never executed at all. ``test_command_resolution.py`` is the
companion that closes that gap — keep both.

They used to be skipped by default as "demonstration, not regression", which
meant a broken filter would also have gone unnoticed. They run normally now:
they are fast, they are pure unit tests, and a filter this load-bearing deserves
a standing guard.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core_management.management.commands.makemigrations import Command


def _fake_migration(name: str, dependencies: list | None = None) -> MagicMock:
    """A stand-in for a ``django.db.migrations.Migration``.

    ``write_migration_files`` reads ``.name`` and rewrites ``.dependencies``, so
    a plain dict or string will not do — which is how these fixtures were
    written before, and why they errored the moment the skip came off.
    """
    migration = MagicMock()
    migration.name = name
    migration.dependencies = list(dependencies or [])
    return migration


class TestMakemigrationsEvenniaFix(SimpleTestCase):
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
        # write_migration_files kicks off MODEL_MAP.md regeneration in a daemon
        # thread whenever it keeps any change. Harmless in production, but in a
        # unit test it is a slow, racy side effect on real files — stub the
        # thread out rather than the function, so the call is still made.
        thread = patch("core_management.management.commands.makemigrations.threading.Thread")
        self.mock_thread = thread.start()
        self.addCleanup(thread.stop)
        # write_migration_files also builds a real MigrationLoader to resolve the
        # graph leaf it rewrites excluded-app dependencies onto. That needs a
        # database connection, which these unit tests have no business opening —
        # so stub it here (SimpleTestCase would otherwise refuse the query, which
        # is the correct refusal). Tests that assert on dependency rewriting
        # re-patch it locally with the leaf they care about.
        loader = patch("core_management.management.commands.makemigrations.MigrationLoader")
        self.mock_loader = loader.start()
        self.addCleanup(loader.stop)
        self.mock_loader.return_value.graph.leaf_nodes.return_value = [
            ("objects", "0013_defaultobject_alter_objectdb_id_defaultcharacter_and_more"),
        ]

    def test_makemigrations_prevents_evennia_phantom_migrations(self):
        """Test that our makemigrations command prevents phantom Evennia migrations."""
        command = Command()
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        # Mock changes that would include Evennia apps (the problematic scenario)
        fake_changes = {
            "objects": [_fake_migration("0014_defaultobject_and_more")],
            "accounts": [_fake_migration("0013_defaultaccount_and_more")],
            "test_phantom_migration_app": [_fake_migration("0001_initial")],
        }

        # Mock the parent write_migration_files to capture what gets passed
        with patch(
            "django.core.management.commands.makemigrations.Command.write_migration_files",
        ) as mock_parent_write:
            mock_parent_write.return_value = (None, None)

            # Call our overridden write_migration_files method
            command.write_migration_files(fake_changes)

            # Verify the parent method was called
            assert mock_parent_write.called

            # Get the filtered changes that were passed to the parent
            call_args = mock_parent_write.call_args[0][0]  # First positional arg

            # Assert that Evennia apps were filtered out
            assert "objects" not in call_args, "Evennia 'objects' app should have been filtered out"
            assert "accounts" not in call_args, (
                "Evennia 'accounts' app should have been filtered out"
            )

            # Assert that our test app was kept
            assert "test_phantom_migration_app" in call_args, (
                "Our custom app should have been preserved"
            )

            # Verify warning messages were displayed for excluded apps
            assert self.mock_stdout.write.called, "Warning messages should have been displayed"

    def test_replaces_dependencies_for_excluded_apps(self):
        """Test dependencies on excluded apps use existing migrations."""
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
                "core_management.management.commands.makemigrations.MigrationLoader",
            ) as mock_loader,
            patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files",
            ) as mock_parent,
        ):
            mock_loader.return_value.graph.leaf_nodes.return_value = [
                ("objects", "0001_initial"),
            ]
            mock_parent.return_value = (None, None)

            command.write_migration_files(fake_changes)

        assert fake_migration.dependencies == [("objects", "0001_initial")], (
            "Dependency should point to existing migration"
        )

    def test_does_not_replace_existing_dependency(self):
        """Test existing dependencies on excluded apps remain unchanged."""
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
                "core_management.management.commands.makemigrations.MigrationLoader",
            ) as mock_loader,
            patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files",
            ) as mock_parent,
        ):
            mock_loader.return_value.graph.leaf_nodes.return_value = [
                ("objects", "0002_real"),
            ]
            mock_parent.return_value = (None, None)

            command.write_migration_files(fake_changes)

        assert fake_migration.dependencies == [("objects", "0001_initial")], (
            "Existing dependency should remain unchanged"
        )

    def test_excluded_apps_list_comprehensive(self):
        """Test that our EXCLUDED_APPS list covers the problematic Evennia apps."""
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
            assert app in command.EXCLUDED_APPS, (
                f"Critical Evennia app '{app}' is not in EXCLUDED_APPS! This could "
                "allow phantom migrations."
            )

    def test_proof_of_problem_without_fix(self):
        """
        Test that demonstrates the problem EXISTS without our fix.

        This test patches out our EXCLUDED_APPS to show that without
        the fix, phantom migrations would be created.
        """
        # Simulate the problematic changes Django detects
        fake_changes = {
            "objects": [_fake_migration("0014_defaultobject_and_more")],
            "accounts": [_fake_migration("0013_defaultaccount_and_more")],
            "test_phantom_migration_app": [_fake_migration("0001_initial")],
        }

        # Test WITHOUT our fix (empty EXCLUDED_APPS)
        with patch.object(Command, "EXCLUDED_APPS", set()):
            command = Command()
            command.stdout = self.mock_stdout
            command.style = self.mock_style

            # Mock write_migration_files to capture what gets through
            with patch(
                "django.core.management.commands.makemigrations.Command.write_migration_files",
            ) as mock_write:
                mock_write.return_value = (None, None)

                # Call our overridden method (but without EXCLUDED_APPS)
                command.write_migration_files(fake_changes)

                # Get what was passed to the parent (should include Evennia apps)
                call_args = mock_write.call_args[0][0]

                # Without our fix, Evennia apps would get through
                assert "objects" in call_args, (
                    "Without our fix, 'objects' app should create phantom migration"
                )
                assert "accounts" in call_args, (
                    "Without our fix, 'accounts' app should create phantom migration"
                )

        # Now test WITH our fix (normal EXCLUDED_APPS)
        command = Command()  # Fresh instance with normal EXCLUDED_APPS
        command.stdout = self.mock_stdout
        command.style = self.mock_style

        with patch(
            "django.core.management.commands.makemigrations.Command.write_migration_files",
        ) as mock_write:
            mock_write.return_value = (None, None)

            command.write_migration_files(fake_changes)

            call_args = mock_write.call_args[0][0]

            # WITH our fix, Evennia apps should be filtered out
            assert "objects" not in call_args, "With our fix, 'objects' app should be filtered out"
            assert "accounts" not in call_args, (
                "With our fix, 'accounts' app should be filtered out"
            )
            assert "test_phantom_migration_app" in call_args, (
                "Our custom app should still get through"
            )
