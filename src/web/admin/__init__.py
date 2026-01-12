"""Custom Django admin site for Arx II with app grouping."""

from django.contrib import admin


class ArxAdminSite(admin.AdminSite):
    """
    Custom admin site that groups models by app and organizes apps into
    logical categories (World → Players → System).
    """

    site_header = "Arx II Administration"
    site_title = "Arx II Admin"
    index_title = "Game Management"

    # Define app groups and their priority order.
    # IMPORTANT: When adding new Django apps, add them to the appropriate group:
    #   - world: Game content apps (characters, stories, realms, etc.)
    #   - players: User/account management apps
    #   - system: Infrastructure and behavior apps
    # Apps not listed here will appear in an "Other" group at the end.
    APP_GROUPS = {
        "world": [
            "character_creation",
            "character_sheets",
            "classes",
            "progression",
            "realms",
            "roster",
            "scenes",
            "stories",
            "traits",
        ],
        "players": [
            "account",
            "socialaccount",
            "evennia_extensions",
        ],
        "system": [
            "behaviors",
            "core_management",
            "flows",
            "admin",
            "auth",
            "contenttypes",
            "sessions",
            "sites",
        ],
    }

    # Group display names for headers
    GROUP_NAMES = {
        "world": "World",
        "players": "Players",
        "system": "System",
        "other": "Other",
    }

    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site, organized into three groups.
        """
        # Get the default app list from Django
        app_dict = self._build_app_dict(request, app_label)

        # Create a mapping of app_label to group name
        app_to_group = {}
        for group_name, app_labels in self.APP_GROUPS.items():
            for label in app_labels:
                app_to_group[label] = group_name

        # Sort apps into groups
        grouped_apps = {"world": [], "players": [], "system": [], "other": []}

        for app in app_dict.values():
            app_label = app["app_label"]
            group = app_to_group.get(app_label, "other")

            # Sort models alphabetically within each app
            app["models"].sort(key=lambda x: x["name"])

            # Add group metadata for template rendering
            app["app_group"] = group
            app["app_group_name"] = self.GROUP_NAMES[group]

            grouped_apps[group].append(app)

        # Sort apps within each group alphabetically by app name
        for group in grouped_apps.values():
            group.sort(key=lambda x: x["name"])

        # Combine groups in priority order: World → Players → System → Other
        return (
            grouped_apps["world"]
            + grouped_apps["players"]
            + grouped_apps["system"]
            + grouped_apps["other"]
        )


# Create the custom admin site instance
arx_admin_site = ArxAdminSite(name="arx_admin")
