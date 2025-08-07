"""
Custom makemigrations command that prevents creating migrations in Evennia library apps.

This command automatically specifies our custom apps when running makemigrations
to avoid the issue where Django tries to create migrations in Evennia's library
for proxy models (typeclasses) that reference Evennia models via ForeignKey.
"""

from django.core.management.commands.makemigrations import Command as BaseCommand


class Command(BaseCommand):
    """Override makemigrations to default to our custom apps only."""

    # Our custom apps that should have migrations generated
    OUR_APPS = [
        "flows",
        "evennia_extensions",
        "roster",
        "traits",
        "behaviors",
    ]

    # Evennia apps that we should ignore when creating migrations
    EVENNIA_APPS = {
        "accounts",
        "objects",
        "scripts",
        "comms",
        "help",
        "typeclasses",
        "server",
        "sessions",
    }

    def handle(self, *app_labels, **options):
        """Override to default to our apps if no apps specified."""

        # If no specific apps provided, default to our custom apps only
        if not app_labels:
            app_labels = self.OUR_APPS
            self.stdout.write(
                self.style.SUCCESS(
                    f"No apps specified, defaulting to our custom apps: {', '.join(app_labels)}"
                )
            )

        # Call the parent command with our app labels
        return super().handle(*app_labels, **options)

    def write_migration_files(self, changes, update_previous_migration_paths=None):
        """Override to filter out Evennia app migrations before writing."""

        # Filter out changes to Evennia apps
        filtered_changes = {}
        for app_label, operations in changes.items():
            if app_label not in self.EVENNIA_APPS:
                filtered_changes[app_label] = operations
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Ignoring proxy model migration for Evennia app: {app_label}"
                    )
                )

        # Call parent with filtered changes
        return super().write_migration_files(
            filtered_changes, update_previous_migration_paths
        )
