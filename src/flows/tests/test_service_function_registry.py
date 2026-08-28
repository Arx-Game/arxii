"""Service-function registry: lazy-load guard + dotted-path resolution."""

from django.test import SimpleTestCase

from flows import service_functions


class RegistryTests(SimpleTestCase):
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
