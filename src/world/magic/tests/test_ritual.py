"""Tests for Ritual model fields."""

from django.test import TestCase

from world.magic.factories import RitualFactory


class RitualInputSchemaTests(TestCase):
    """Tests for Ritual.input_schema JSONField."""

    def test_ritual_input_schema_defaults_to_none(self):
        """input_schema is optional; rituals without one return None."""
        ritual = RitualFactory()
        self.assertIsNone(ritual.input_schema)

    def test_ritual_input_schema_persists_dict(self):
        """input_schema stores arbitrary JSON-serializable dicts."""
        schema = {
            "fields": [{"name": "target_id", "type": "int", "label": "Target", "required": True}]
        }
        ritual = RitualFactory(input_schema=schema)
        ritual.refresh_from_db()
        self.assertEqual(ritual.input_schema, schema)
