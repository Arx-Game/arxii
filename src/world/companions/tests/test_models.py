"""Tests for world.companions models (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.companions.constants import CompanionDomain
from world.companions.factories import CompanionArchetypeFactory


class CompanionArchetypeTests(TestCase):
    def test_str_is_name(self) -> None:
        archetype = CompanionArchetypeFactory(name="Direwolf", domain=CompanionDomain.BEAST)

        self.assertEqual(str(archetype), "Direwolf")

    def test_domain_defaults_to_beast(self) -> None:
        archetype = CompanionArchetypeFactory()

        self.assertEqual(archetype.domain, CompanionDomain.BEAST)

    def test_name_is_unique(self) -> None:
        CompanionArchetypeFactory(name="Hawk")

        with self.assertRaises(Exception):  # noqa: B017 — IntegrityError vs ValidationError varies
            from world.companions.models import CompanionArchetype

            CompanionArchetype.objects.create(
                name="Hawk",
                domain=CompanionDomain.BEAST,
                bind_difficulty=10,
                capacity_cost=5,
            )
