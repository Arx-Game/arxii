"""``makemigrations`` must resolve to OUR command, not django-linear-migrations' (#2885).

``core_management`` and ``django_linear_migrations`` both ship a
``makemigrations``. Only one can win, and which one is decided entirely by
INSTALLED_APPS order — in the counter-intuitive direction, since Django's
``get_commands()`` walks ``reversed(apps.get_app_configs())`` and ``update()``s,
so the app listed EARLIEST wins.

Ours lost from the day ``django_linear_migrations`` was added until #2885. The
phantom-Evennia-migration filter in
``core_management.management.commands.makemigrations`` was dead code the whole
time, and every migration generated in that window wrote a phantom Evennia
migration into the generating venv and then depended on it — surfacing in CI as
``NodeNotFoundError`` on jobs that never mention migrations (``ty``,
``api-types-drift``).

Nothing caught it. ``test_makemigrations_fix.py`` imports the command class
directly and asserts on its behavior, so it passes whether or not Django ever
runs that class — which is exactly the blind spot these tests close. **These
assert on resolution, never on the class in isolation.**
"""

from __future__ import annotations

from django.core.management import get_commands, load_command_class
from django.test import SimpleTestCase


class MakemigrationsResolutionTests(SimpleTestCase):
    def test_makemigrations_resolves_to_core_management(self) -> None:
        """The whole bug in one assertion.

        If this fails, INSTALLED_APPS was reordered so that another app's
        ``makemigrations`` shadows ours — see the ORDER IS LOAD-BEARING comment
        in ``server/conf/settings.py``. Do not "fix" it by deleting this test.
        """
        assert get_commands()["makemigrations"] == "core_management"

    def test_resolved_command_carries_the_phantom_filter(self) -> None:
        """Resolution alone is not enough — the winner must be the filtering one."""
        command = load_command_class("core_management", "makemigrations")

        assert hasattr(command, "EXCLUDED_APPS")
        assert "objects" in command.EXCLUDED_APPS

    def test_resolved_command_still_carries_the_linear_migrations_sentinel(self) -> None:
        """Winning must not cost us #991's max_migration.txt sentinel.

        Ours subclasses django-linear-migrations' command precisely so both
        behaviors survive; a future reparent onto Django's base would silently
        drop the sentinel that keeps the merge queue from hitting multiple leaf
        nodes.
        """
        from django_linear_migrations.management.commands.makemigrations import (
            Command as LinearMigrationsCommand,
        )

        command = load_command_class("core_management", "makemigrations")

        assert isinstance(command, LinearMigrationsCommand)

    def test_linear_migrations_keeps_its_own_commands(self) -> None:
        """Only ``makemigrations`` overlaps; the reorder must not shadow the rest."""
        commands = get_commands()

        for name in ("squashmigrations", "rebase_migration", "create_max_migration_files"):
            assert commands[name] == "django_linear_migrations", name
