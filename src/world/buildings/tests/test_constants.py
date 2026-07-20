"""Tests for shared buildings constants."""

from django.test import TestCase

from world.buildings.constants import COPPERS_PER_PROGRESS_POINT


class SharedConstantsTests(TestCase):
    def test_coppers_per_progress_point_is_positive(self):
        assert COPPERS_PER_PROGRESS_POINT > 0
