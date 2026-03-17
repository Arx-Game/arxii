"""Custom makemigrations command that avoids phantom Evennia migrations.

This command automatically specifies our custom apps when running makemigrations
to avoid the issue where Django tries to create migrations in Evennia's library
for proxy models (typeclasses) that reference Evennia models via ForeignKey.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
from typing import Any, ClassVar

from django.core.management.commands.makemigrations import Command as BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader

logger = logging.getLogger(__name__)


def _regenerate_model_map() -> None:
    try:
        tools_dir = str(Path(__file__).resolve().parents[4] / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from introspect_models import write_model_map  # noqa: PLC0415

        write_model_map()
    except Exception:
        logger.exception("MODEL_MAP.md regeneration failed")


class Command(BaseCommand):
    """Override makemigrations to default to our custom apps only."""

    # Apps that we should exclude from migrations (Evennia + common third-party)
    EXCLUDED_APPS: ClassVar[set[str]] = {
        # Evennia core apps
        "accounts",
        "objects",
        "scripts",
        "comms",
        "help",
        "typeclasses",
        "server",
        "sessions",
        "web",
        "idmapper",
    }

    def write_migration_files(
        self,
        changes: dict[str, Any],
        update_previous_migration_paths: dict[str, str] | None = None,
    ) -> None:
        """Override to filter out Evennia migrations and fix dependencies.

        Args:
            changes: Mapping of app labels to lists of migrations.
            update_previous_migration_paths: Previous migration path updates.
        """

        loader = MigrationLoader(connection, ignore_no_migrations=True)

        ignored_migrations = {
            app: {migration.name for migration in migrations}
            for app, migrations in changes.items()
            if app in self.EXCLUDED_APPS
        }

        filtered_changes: dict[str, Any] = {}
        for app_label, migrations in changes.items():
            if app_label in self.EXCLUDED_APPS:
                self.stdout.write(
                    self.style.WARNING(
                        f"Ignoring proxy model migration for excluded app: {app_label}",
                    ),
                )
                continue

            for migration in migrations:
                new_deps = []
                for dep_app, dep_name in migration.dependencies:
                    if dep_app in ignored_migrations and dep_name in ignored_migrations[dep_app]:
                        leaves = loader.graph.leaf_nodes(dep_app)
                        if leaves:
                            resolved_dep_name = leaves[0][1]
                        else:
                            resolved_dep_name = dep_name
                    else:
                        resolved_dep_name = dep_name
                    new_deps.append((dep_app, resolved_dep_name))
                migration.dependencies = new_deps
            filtered_changes[app_label] = migrations

        result = super().write_migration_files(
            filtered_changes,
            update_previous_migration_paths,
        )

        if filtered_changes:
            thread = threading.Thread(target=_regenerate_model_map, daemon=True)
            thread.start()
            self.stdout.write(
                self.style.SUCCESS("MODEL_MAP.md regeneration started in background.")
            )

        return result
