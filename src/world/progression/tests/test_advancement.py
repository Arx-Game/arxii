"""Model-shape tests for ClassLevelAdvancement receipt (#1352)."""

from django.test import TestCase

from world.progression.models import ClassLevelAdvancement


class ClassLevelAdvancementModelTests(TestCase):
    def test_fields_and_str(self):
        fields = {f.name for f in ClassLevelAdvancement._meta.get_fields()}
        assert {
            "character_sheet",
            "character_class",
            "officiant",
            "ritual",
            "scene",
            "declaration_interaction",
            "level_before",
            "level_after",
            "created_at",
        } <= fields
