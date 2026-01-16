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
            "forms",
            "progression",
            "realms",
            "roster",
            "scenes",
            "species",
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
        "recent": "Recent",
        "world": "World",
        "players": "Players",
        "system": "System",
        "other": "Other",
    }

    def get_app_list(self, request, app_label=None):
        """Return app list with Recent section at top."""
        from web.admin.models import AdminPinnedModel  # noqa: PLC0415

        app_dict = self._build_app_dict(request, app_label)

        # Build Recent section from pinned models
        recent_models = []
        pinned = AdminPinnedModel.objects.all()
        for pin in pinned:
            app_key = pin.app_label
            if app_key in app_dict:
                for model in app_dict[app_key]["models"]:
                    if model["object_name"].lower() == pin.model_name.lower():
                        recent_models.append(
                            {
                                **model,
                                "pinned": True,
                            }
                        )
                        break

        # Create app_to_group mapping
        app_to_group = {}
        for group_name, app_labels in self.APP_GROUPS.items():
            for label in app_labels:
                app_to_group[label] = group_name

        # Sort apps into groups
        grouped_apps = {
            "recent": [],
            "world": [],
            "players": [],
            "system": [],
            "other": [],
        }

        # Add Recent as a pseudo-app if there are pinned models
        if recent_models:
            grouped_apps["recent"].append(
                {
                    "name": "Recent",
                    "app_label": "_recent",
                    "app_url": "",
                    "has_module_perms": True,
                    "models": recent_models,
                    "app_group": "recent",
                    "app_group_name": "Recent",
                }
            )

        for app in app_dict.values():
            app_label_key = app["app_label"]
            group = app_to_group.get(app_label_key, "other")
            app["models"].sort(key=lambda x: x["name"])
            app["app_group"] = group
            app["app_group_name"] = self.GROUP_NAMES[group]
            grouped_apps[group].append(app)

        for group in grouped_apps.values():
            group.sort(key=lambda x: x["name"])

        return (
            grouped_apps["recent"]
            + grouped_apps["world"]
            + grouped_apps["players"]
            + grouped_apps["system"]
            + grouped_apps["other"]
        )


# Create the custom admin site instance
arx_admin_site = ArxAdminSite(name="arx_admin")
