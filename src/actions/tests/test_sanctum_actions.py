from django.test import TestCase

from actions.definitions.sanctum import SanctumActionBase


class SanctumActionBaseTests(TestCase):
    def test_base_is_self_targeted_magic(self):
        base = SanctumActionBase()
        self.assertEqual(base.category, "magic")
        self.assertEqual(base.target_type.name, "SELF")
