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

    def _superuser_app_list(self):
        """Return ``get_app_list`` output for a fully-privileged request."""
        request = self.factory.get("/admin/")
        User = get_user_model()
        request.user = User(username="test", is_staff=True, is_superuser=True)
        return self.site.get_app_list(request)

    def test_arxii_mega_entry_is_split_by_domain(self):
        """The collapsed ``arxii`` app_dict entry must not survive as one bucket.

        #2906 merged 66 world.* apps onto one Django app_label ("arxii"),
        which collapsed the admin index into a single 539-model list. This
        pins the regression: the index must expose many first-party entries,
        never a single merged one.
        """
        app_list = self._superuser_app_list()

        first_party_labels = {app["app_label"] for app in app_list if app["app_label"] != "_recent"}

        self.assertNotIn(
            "arxii",
            first_party_labels,
            "the collapsed app_label should never appear directly in the admin index",
        )
        # Well above 1: a regression back to a single merged bucket must fail loudly.
        self.assertGreater(
            len(first_party_labels),
            20,
            "admin index should list many per-domain entries, not one merged bucket",
        )

    def test_distinct_domains_land_in_separate_entries(self):
        """Models from distinct authoring domains must not share an app_dict entry."""
        app_list = self._superuser_app_list()
        by_label = {app["app_label"]: app for app in app_list}

        for domain in ("magic", "roster", "progression"):
            self.assertIn(domain, by_label, f"expected a distinct {domain!r} admin entry")

        magic_models = {m["object_name"] for m in by_label["magic"]["models"]}
        roster_models = {m["object_name"] for m in by_label["roster"]["models"]}
        progression_models = {m["object_name"] for m in by_label["progression"]["models"]}

        self.assertTrue(magic_models, "magic entry should have models")
        self.assertTrue(roster_models, "roster entry should have models")
        self.assertTrue(progression_models, "progression entry should have models")
        self.assertFalse(magic_models & roster_models, "magic/roster entries should not overlap")
        self.assertFalse(
            roster_models & progression_models,
            "roster/progression entries should not overlap",
        )

    def test_domain_group_assignment_matches_pre_collapse_expectation(self):
        """Split entries should land in the group APP_GROUPS assigns their domain to."""
        app_list = self._superuser_app_list()
        by_label = {app["app_label"]: app for app in app_list}

        self.assertEqual(by_label["roster"]["app_group"], "world")
        self.assertEqual(by_label["progression"]["app_group"], "world")
        self.assertEqual(by_label["evennia_extensions"]["app_group"], "players")
        self.assertEqual(by_label["auth"]["app_group"], "system")
        self.assertEqual(by_label["sites"]["app_group"], "system")

    def test_non_first_party_apps_still_present_and_grouped(self):
        """Genuinely separate installed apps (never touched by #2906) still appear."""
        app_list = self._superuser_app_list()
        labels = {app["app_label"] for app in app_list}

        for label in ("socialaccount", "auth", "sites"):
            self.assertIn(label, labels, f"{label} should still be its own admin entry")

    def test_split_entry_model_urls_still_resolve(self):
        """A split pseudo-entry's models must keep working change-list links.

        The pseudo-entry's own app_label is a domain (not a real Django app
        label), but each model's admin_url is built by Django's own
        _build_app_dict from the real (collapsed) app_label, so it must
        still point at a real, non-empty URL.
        """
        app_list = self._superuser_app_list()
        by_label = {app["app_label"]: app for app in app_list}

        roster_models = by_label["roster"]["models"]
        self.assertTrue(roster_models)
        for model in roster_models:
            if model.get("admin_url"):
                # Built from the real (collapsed) app_label, not the domain
                # pseudo-label -- links must resolve under /admin/arxii/...
                self.assertIn("/admin/arxii/", model["admin_url"])
