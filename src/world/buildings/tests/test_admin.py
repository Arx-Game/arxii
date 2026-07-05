"""Tests for buildings admin registrations."""

from django.contrib import admin
from django.test import TestCase

from world.buildings.models import MaterialLoreEffect


class MaterialLoreEffectAdminTests(TestCase):
    def test_material_lore_effect_is_registered(self) -> None:
        assert MaterialLoreEffect in admin.site._registry
