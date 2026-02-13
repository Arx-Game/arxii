"""Tests for custom Arx admin site."""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from web.admin import ArxAdminSite, arx_admin_site


class ArxAdminSiteTestCase(TestCase):
    """Test cases for the custom ArxAdminSite."""

    def setUp(self):
        self.site = arx_admin_site
        self.factory = RequestFactory()

    def test_site_is_instance_of_admin_site(self):
        """ArxAdminSite should be a proper AdminSite subclass."""
        self.assertIsInstance(self.site, AdminSite)
        self.assertIsInstance(self.site, ArxAdminSite)

    def test_site_branding(self):
        """Site should have custom Arx II branding."""
        self.assertEqual(self.site.site_header, "Arx II Administration")
        self.assertEqual(self.site.site_title, "Arx II Admin")
        self.assertEqual(self.site.index_title, "Game Management")

    def test_app_groups_defined(self):
        """APP_GROUPS should define three main groups."""
        self.assertIn("world", self.site.APP_GROUPS)
        self.assertIn("players", self.site.APP_GROUPS)
        self.assertIn("system", self.site.APP_GROUPS)

    def test_group_names_defined(self):
        """GROUP_NAMES should define display names for all groups."""
        self.assertEqual(self.site.GROUP_NAMES["world"], "World")
        self.assertEqual(self.site.GROUP_NAMES["players"], "Players")
        self.assertEqual(self.site.GROUP_NAMES["system"], "System")
        self.assertEqual(self.site.GROUP_NAMES["other"], "Other")

    def test_get_app_list_returns_list(self):
        """get_app_list should return a list."""
        User = get_user_model()
        request = self.factory.get("/admin/")
        request.user = User(username="test", is_staff=True, is_superuser=True)
        app_list = self.site.get_app_list(request)
        self.assertIsInstance(app_list, list)

    def test_get_app_list_adds_group_metadata(self):
        """
        get_app_list should add app_group and app_group_name to each app.

        This test uses the actual installed apps to verify metadata is added.
        """
        request = self.factory.get("/admin/")
        # Create a mock user with appropriate permissions
        User = get_user_model()
        request.user = User(username="test", is_staff=True, is_superuser=True)

        app_list = self.site.get_app_list(request)

        # Check that apps have group metadata
        for app in app_list:
            self.assertIn("app_group", app)
            self.assertIn("app_group_name", app)
            # Verify group name is one of our defined groups
            self.assertIn(
                app["app_group"],
                ["world", "players", "system", "other"],
            )

    def test_get_app_list_sorts_models_alphabetically(self):
        """Models within each app should be sorted alphabetically by name."""
        request = self.factory.get("/admin/")
        User = get_user_model()
        request.user = User(username="test", is_staff=True, is_superuser=True)

        app_list = self.site.get_app_list(request)

        # Check that models are sorted alphabetically in each app
        for app in app_list:
            if app.get("models"):
                model_names = [model["name"] for model in app["models"]]
                sorted_names = sorted(model_names)
                self.assertEqual(
                    model_names,
                    sorted_names,
                    f"Models in {app['name']} app are not sorted alphabetically",
                )

    def test_get_app_list_groups_apps_in_correct_order(self):
        """
        Apps should be grouped and appear in order: World, Players, System, Other.

        This tests that if we have apps from multiple groups, they appear
        in the expected sequence.
        """
        request = self.factory.get("/admin/")
        User = get_user_model()
        request.user = User(username="test", is_staff=True, is_superuser=True)

        app_list = self.site.get_app_list(request)

        if not app_list:
            self.skipTest("No apps registered in admin")

        # Track which groups appear and in what order
        seen_groups = []
        for app in app_list:
            group = app["app_group"]
            if group not in seen_groups:
                seen_groups.append(group)

        # Verify groups appear in the expected order
        expected_order = ["world", "players", "system", "other"]
        # Filter to only groups that actually appeared
        expected_filtered = [g for g in expected_order if g in seen_groups]

        self.assertEqual(
            seen_groups,
            expected_filtered,
            "App groups do not appear in expected order (World → Players → System → Other)",
        )

    def test_world_apps_correctly_grouped(self):
        """World apps should be in the world group."""
        world_apps = self.site.APP_GROUPS["world"]

        # Verify key world apps are listed
        expected_apps = [
            "character_creation",
            "character_sheets",
            "roster",
            "traits",
        ]
        for app in expected_apps:
            self.assertIn(
                app,
                world_apps,
                f"{app} should be in world group",
            )

    def test_players_apps_correctly_grouped(self):
        """Player-related apps should be in the players group."""
        players_apps = self.site.APP_GROUPS["players"]

        expected_apps = ["account", "socialaccount", "evennia_extensions"]
        for app in expected_apps:
            self.assertIn(
                app,
                players_apps,
                f"{app} should be in players group",
            )

    def test_system_apps_correctly_grouped(self):
        """System apps should be in the system group."""
        system_apps = self.site.APP_GROUPS["system"]

        expected_apps = ["auth", "contenttypes", "sessions"]
        for app in expected_apps:
            self.assertIn(
                app,
                system_apps,
                f"{app} should be in system group",
            )
