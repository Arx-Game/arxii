"""Service-function registry: lazy-load guard + dotted-path resolution."""

from django.test import SimpleTestCase

from flows import service_functions


class RegistryTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        # Module-global registry state (SERVICE_FUNCTIONS, _loaded) persists
        # across the whole test process, so which test happens to run first
        # decides whether `_ensure_loaded()` has already fired. Save + reset
        # both here so THIS test controls "before first lookup" itself,
        # rather than depending on suite ordering (#3417 review finding 2).
        self._saved_functions = dict(service_functions.SERVICE_FUNCTIONS)
        self._saved_loaded = service_functions._loaded
        service_functions.SERVICE_FUNCTIONS.clear()
        service_functions._loaded = False

    def tearDown(self):
        service_functions.SERVICE_FUNCTIONS.clear()
        service_functions.SERVICE_FUNCTIONS.update(self._saved_functions)
        service_functions._loaded = self._saved_loaded
        super().tearDown()

    def test_register_before_first_lookup_does_not_block_hooks(self):
        service_functions.register_service_function("plan_test_fn", lambda: None)
        listed = service_functions.list_service_functions()
        self.assertIn("plan_test_fn", listed)
        self.assertIn("move_object", listed)  # hook-loaded from movement.py

    def test_dotted_path_resolution_still_works(self):
        fn = service_functions.get_service_function(
            "flows.service_functions.movement.redirect_move"
        )
        self.assertTrue(callable(fn))
