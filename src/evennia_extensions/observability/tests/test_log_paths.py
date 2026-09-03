"""Tests for evennia_extensions.observability.log_paths."""

from django.test import SimpleTestCase


class LogFilePathsTests(SimpleTestCase):
    """All four Evennia log files follow the directory they are given."""

    def test_all_four_paths_live_under_the_given_directory(self) -> None:
        from evennia_extensions.observability.log_paths import log_file_paths

        paths = log_file_paths("/var/log/arxii")

        self.assertEqual(paths.server, "/var/log/arxii/server.log")
        self.assertEqual(paths.portal, "/var/log/arxii/portal.log")
        self.assertEqual(paths.http, "/var/log/arxii/http_requests.log")
        self.assertEqual(paths.lockwarning, "/var/log/arxii/lockwarnings.log")

    def test_settings_derive_from_log_dir(self) -> None:
        """settings.py must re-derive every file setting from LOG_DIR."""
        from django.conf import settings

        self.assertEqual(settings.SERVER_LOG_FILE, f"{settings.LOG_DIR}/server.log")
        self.assertEqual(settings.PORTAL_LOG_FILE, f"{settings.LOG_DIR}/portal.log")
        self.assertEqual(settings.HTTP_LOG_FILE, f"{settings.LOG_DIR}/http_requests.log")
        self.assertEqual(settings.LOCKWARNING_LOG_FILE, f"{settings.LOG_DIR}/lockwarnings.log")
