"""Tests for MissionCategory + MissionTemplate.categories M2M (Phase B, B1).

A lookup model that lets a MissionTemplate carry multi-valued content-type
tags (assassination, courtly, heist, …). Mirrors the mechanics.ChallengeCategory
shape: NaturalKeyMixin + SharedMemoryModel with a unique name and an optional
description.
"""

from django.db import IntegrityError
from django.test import TestCase

from world.missions.factories import (
    MissionCategoryFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionCategory, MissionTemplate


class MissionCategoryModelTests(TestCase):
    """Lookup model + M2M attachment to MissionTemplate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = MissionCategoryFactory(name="Assassination")
        cls.template = MissionTemplateFactory(name="cat-tmpl")

    def test_round_trips_by_name(self) -> None:
        fetched = MissionCategory.objects.get(name="Assassination")
        self.assertEqual(fetched, self.category)

    def test_name_is_unique(self) -> None:
        with self.assertRaises(IntegrityError):
            MissionCategory.objects.create(name="Assassination")

    def test_template_categories_defaults_empty(self) -> None:
        self.assertEqual(list(self.template.categories.all()), [])

    def test_template_can_attach_multiple_categories(self) -> None:
        courtly = MissionCategoryFactory(name="Courtly")
        self.template.categories.add(self.category, courtly)
        fetched = MissionTemplate.objects.get(pk=self.template.pk)
        self.assertEqual(
            {c.name for c in fetched.categories.all()},
            {"Assassination", "Courtly"},
        )

    def test_category_reverse_relation(self) -> None:
        # MissionCategory.templates is the reverse accessor.
        self.template.categories.add(self.category)
        self.assertIn(self.template, self.category.templates.all())

    def test_display_order_defaults_zero(self) -> None:
        # No Meta.ordering on the model — callers explicitly
        # order_by("display_order", "name"); default is 0.
        self.assertEqual(self.category.display_order, 0)

    def test_display_order_round_trips(self) -> None:
        ordered = MissionCategoryFactory(name="ordered-cat", display_order=42)
        ordered.refresh_from_db()
        self.assertEqual(ordered.display_order, 42)
