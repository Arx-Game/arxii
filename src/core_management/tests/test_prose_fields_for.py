"""``prose_fields_for`` (#3019): the promoted single-model classifier.

Promoted from ``test_prose_credits._text_fields`` + the ``PROSE_FIELD_NAMES``
membership check so production code (the authoring workbench) and the guard
tests in ``test_prose_credits.py`` share one definition.
"""

from django.test import SimpleTestCase

from core_management.prose_fields import prose_fields_for
from world.contributors.models import ContentContributor
from world.traits.models import Trait


class ProseFieldsForTests(SimpleTestCase):
    def test_returns_exactly_the_prose_fields(self):
        # Trait: description is prose; name is an identifier (NON_PROSE); the
        # two choice-bearing CharFields (trait_type, category) are excluded
        # outright because they carry choices, prose or not.
        self.assertEqual(prose_fields_for(Trait), ["description"])

    def test_a_model_with_no_prose_fields_returns_empty(self):
        # ContentContributor's only free-text fields are "name" and "notes",
        # both NON_PROSE_TEXT_FIELDS.
        self.assertEqual(prose_fields_for(ContentContributor), [])
