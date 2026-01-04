"""Check for missing migrations without querying the database."""

from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path
import sys

import django
from django.apps import apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
ENV_FILE = SRC_DIR / ".env"


def setup_environment() -> None:
    """Configure the Django environment for migration checking."""
    os.chdir(SRC_DIR)
    sys.path.insert(0, str(SRC_DIR))

    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)

    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        os.environ["DJANGO_SETTINGS_MODULE"] = "server.conf.settings"


def collect_changes(excluded_apps: set[str]) -> dict[str, list]:
    """Collect migration changes without consulting the database.

    Returns:
        A mapping of app labels to migration instances.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    autodetector = MigrationAutodetector(
        loader.project_state(),
        ProjectState.from_apps(apps),
    )
    changes = autodetector.changes(graph=loader.graph)

    return {
        app_label: migrations
        for app_label, migrations in changes.items()
        if app_label not in excluded_apps
    }


def main() -> int:
    """Run the migration check and report missing migrations.

    Returns:
        Process exit code (0 when clean, 1 when migrations are missing).
    """
    setup_environment()
    django.setup()

    excluded_apps = set(get_excluded_apps())
    changes = collect_changes(excluded_apps)

    if not changes:
        print("No missing migrations detected.")
        return 0

    print("Missing migrations detected:")
    for app_label in sorted(changes):
        migrations = changes[app_label]
        names = ", ".join(migration.name for migration in migrations)
        print(f"- {app_label}: {names}")

    return 1


def get_excluded_apps() -> set[str]:
    """Load excluded app labels from the custom makemigrations command."""
    command_module = import_module(
        "core_management.management.commands.makemigrations",
    )

    return command_module.Command.EXCLUDED_APPS


if __name__ == "__main__":
    raise SystemExit(main())
