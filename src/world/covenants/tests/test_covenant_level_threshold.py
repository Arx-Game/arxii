from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.factories import CovenantLevelThresholdFactory
from world.covenants.models import CovenantLevelThreshold


class CovenantLevelThresholdTests(TestCase):
    def test_unique_level(self):
        CovenantLevelThresholdFactory(level=1, required_legend=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantLevelThreshold.objects.create(level=1, required_legend=50)

    def test_string_repr(self):
        threshold = CovenantLevelThresholdFactory(level=5, required_legend=700)
        self.assertEqual(str(threshold), "Level 5 (≥ 700 legend)")
