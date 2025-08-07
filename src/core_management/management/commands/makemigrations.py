"""
Custom makemigrations command that prevents creating migrations in Evennia library apps.

This command automatically specifies our custom apps when running makemigrations
to avoid the issue where Django tries to create migrations in Evennia's library
for proxy models (typeclasses) that reference Evennia models via ForeignKey.
"""

from django.core.management.commands.makemigrations import Command as BaseCommand


class Command(BaseCommand):
    """Override makemigrations to default to our custom apps only."""

    # Apps that we should exclude from migrations (Evennia + common third-party)
    EXCLUDED_APPS = {
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

    def write_migration_files(self, changes, update_previous_migration_paths=None):
        """Override to filter out Evennia app migrations before writing."""

        # Filter out changes to excluded apps
        filtered_changes = {}
        for app_label, operations in changes.items():
            if app_label not in self.EXCLUDED_APPS:
                filtered_changes[app_label] = operations
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Ignoring proxy model migration for excluded app: {app_label}"
                    )
                )

        # Call parent with filtered changes
        return super().write_migration_files(
            filtered_changes, update_previous_migration_paths
        )
