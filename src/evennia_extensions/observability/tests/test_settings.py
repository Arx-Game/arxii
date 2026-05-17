from django.test import TestCase, override_settings

from evennia_extensions.observability.settings import observability_config


class ObservabilityConfigTests(TestCase):
    def test_disabled_by_default(self):
        cfg = observability_config()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.port, 9109)

    @override_settings(OBSERVABILITY_ENABLED=True, OBSERVABILITY_PORT=9999)
    def test_reads_overrides(self):
        cfg = observability_config()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.port, 9999)
