"""Tests for world.projects.constants."""

from django.test import TestCase

from world.projects.constants import ProjectKind


class ProjectKindTests(TestCase):
    def test_building_activation_kind_exists(self):
        assert ProjectKind.BUILDING_ACTIVATION == "BUILDING_ACTIVATION"
