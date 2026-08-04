"""Custom Django admin site for Arx II with app grouping."""

from django.contrib import admin

from core.app_domains import domain_of


class ArxAdminSite(admin.AdminSite):
    """
    Custom admin site that groups models by app and organizes apps into
    logical categories (World → Players → System).
    """

    site_header = "Arx II Administration"
    site_title = "Arx II Admin"
    index_title = "Game Management"

    # The single Django app_label the #2906 collapse merged every first-party
    # model onto (see ``world/apps.py``'s ``ArxiiConfig.label``). This is the
    # only app_label ``_split_by_domain``/``_domain_key`` ever need to treat
    # specially -- every other app_dict entry is still a genuinely separate
    # installed Django app, unaffected by the collapse.
    _COLLAPSED_APP_LABEL = "arxii"

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

    def _build_recent_models(self, app_dict, excluded):
        """Build list of pinned models with export exclusion status.

        ``pin.app_label`` holds a *domain* value (``core.app_domains.domain_of``,
        written by ``web.admin.views.toggle_pin_model`` — #2906). ``app_dict``
        here is the ALREADY-``_split_by_domain``-split dict ``get_app_list``
        builds, so its first-party entries are keyed by that same domain
        value and this still keys straight in.
        """
        from web.admin.models import AdminPinnedModel  # noqa: PLC0415

        recent_models = []
        for pin in AdminPinnedModel.objects.all():
            app_key = pin.app_label
            if app_key not in app_dict:
                continue
            for model in app_dict[app_key]["models"]:
                if model["object_name"].lower() == pin.model_name.lower():
                    recent_models.append(
                        {
                            **model,
                            "pinned": True,
                            "export_excluded": (app_key, model["object_name"].lower()) in excluded,
                        }
                    )
                    break
        return recent_models

    @classmethod
    def _domain_key(cls, app):
        """Return the domain bucketing key for an ``app_dict`` entry.

        For every entry EXCEPT the collapsed ``arxii`` one, ``app["app_label"]``
        already *is* the right key — these are genuinely separate installed
        Django apps (``auth``, ``sites``, ``socialaccount``, ...) that #2906
        never touched, so their real app_label is exactly what pre-collapse
        bucketing used. Calling ``domain_of()`` on them is wrong: it recovers
        a domain from the *module* path (``django.contrib.auth.models`` ->
        ``"django"``), which doesn't match their app_label and would silently
        drop them into the "Other" group.

        The one entry that DOES need ``domain_of()`` is ``arxii`` itself,
        since #2906 merged every first-party model onto that single label —
        any model's ``domain_of()`` value stands in for the whole entry.
        In practice ``get_app_list`` splits that entry via
        ``_split_by_domain`` before this is ever called, so this branch is
        defensive (keeps ``_domain_key`` correct if ever called on a
        pre-split ``app_dict``, e.g. directly from a test).
        """
        if app["app_label"] != cls._COLLAPSED_APP_LABEL:
            return app["app_label"]
        models = app.get("models") or []
        if not models:
            return app["app_label"]
        return domain_of(models[0]["model"])

    @staticmethod
    def _domain_display_name(domain):
        """Turn a domain key (e.g. ``"character_creation"``) into a display name."""
        return domain.replace("_", " ").title()

    @classmethod
    def _split_by_domain(cls, app_dict):
        """Split the collapsed ``arxii`` app_dict entry into per-domain pseudo-apps.

        Pre-#2906, one Django app == one domain == one ``app_dict`` entry, so
        the admin index naturally grouped and displayed each domain as its
        own app block. The single-app collapse merged every first-party
        model onto one Django app_label (``arxii``), so ``_build_app_dict``
        now returns exactly one entry holding every first-party model (539
        as of #2906). Splitting that entry back out by ``domain_of()`` here
        restores the pre-collapse entry-per-domain shape for grouping and
        display purposes.

        This never touches ``model["admin_url"]``/``model["add_url"]`` — those
        were already built by Django's own ``_build_app_dict`` from the real
        (collapsed) app_label, so the change-list/add links keep resolving.
        The pseudo-entries' own ``app_url`` is set to ``""`` (like the
        existing "Recent" pseudo-app) rather than a per-domain change-list
        page, since ``admin:app_list`` only accepts real, installed
        app_labels — a domain isn't one.

        Every other (non-collapsed) app_dict entry passes through unchanged:
        those are still genuinely separate installed Django apps (allauth,
        Evennia's own apps, ...) that #2906 never touched.
        """
        split = {}
        for app in app_dict.values():
            if app["app_label"] != cls._COLLAPSED_APP_LABEL:
                split[app["app_label"]] = app
                continue
            domain_groups: dict[str, list] = {}
            for model in app["models"]:
                domain_groups.setdefault(domain_of(model["model"]), []).append(model)
            for domain, models in domain_groups.items():
                split[domain] = {
                    "name": cls._domain_display_name(domain),
                    "app_label": domain,
                    "app_url": "",
                    "has_module_perms": app["has_module_perms"],
                    "models": models,
                }
        return split

    def _mark_export_exclusion(self, app, excluded, app_label_key):
        """Mark export exclusion status on each model in an app."""
        for model in app["models"]:
            model["export_excluded"] = (
                app_label_key,
                model["object_name"].lower(),
            ) in excluded

    def get_app_list(self, request, app_label=None):
        """Return app list with Recent section at top."""
        from web.admin.models import AdminExcludedModel  # noqa: PLC0415

        app_dict = self._build_app_dict(request, app_label)
        # Restore the pre-collapse entry-per-domain shape (#2906 Task 5b):
        # otherwise every first-party model shares one merged "arxii" entry.
        app_dict = self._split_by_domain(app_dict)

        # Get excluded models for export
        excluded = {(e.app_label, e.model_name.lower()) for e in AdminExcludedModel.objects.all()}

        # Build Recent section from pinned models
        recent_models = self._build_recent_models(app_dict, excluded)

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
            app_label_key = self._domain_key(app)
            group = app_to_group.get(app_label_key, "other")
            self._mark_export_exclusion(app, excluded, app_label_key)
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
