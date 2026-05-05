"""Tests for Ritual model fields."""

from django.test import TestCase

from world.magic.factories import RitualFactory


class RitualInputSchemaTests(TestCase):
    """Tests for Ritual.input_schema JSONField."""

    @classmethod
    def setUpTestData(cls):
        cls.ritual = RitualFactory()
        cls.schema = {
            "fields": [{"name": "target_id", "type": "int", "label": "Target", "required": True}]
        }
        cls.ritual_with_schema = RitualFactory(input_schema=cls.schema)

    def test_ritual_input_schema_defaults_to_none(self):
        """input_schema is optional; rituals without one return None."""
        self.assertIsNone(self.ritual.input_schema)

    def test_ritual_input_schema_persists_dict(self):
        """input_schema stores arbitrary JSON-serializable dicts."""
        self.ritual_with_schema.refresh_from_db()
        self.assertEqual(self.ritual_with_schema.input_schema, self.schema)
