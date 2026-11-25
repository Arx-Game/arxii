"""Migration 0485 marks the creation targets whatever case staff wrote them in (#5206).

The natural key of a target compares names case-insensitively (ADR-0163), so a target
authored as "Starting_Technique_Picks" is the same target, and the fill must mark it.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget

fill = import_module("world.migrations.0485_modifiertarget_spent_at_creation_fill")


class SpentAtCreationFillTest(TestCase):
    def test_matches_category_and_name_case_insensitively(self) -> None:
        picks = ModifierTargetFactory(
            name="Starting_Technique_Picks",
            category=ModifierCategoryFactory(name="Character_Creation"),
        )
        other = ModifierTargetFactory(
            name="starting_technique_picks_extra",
            category=ModifierCategoryFactory(name="character_creation"),
        )

        fill.mark_spent_at_creation(apps, None)

        self.assertTrue(ModifierTarget.objects.get(pk=picks.pk).spent_at_creation)
        self.assertFalse(ModifierTarget.objects.get(pk=other.pk).spent_at_creation)
