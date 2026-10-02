"""Demo-fidelity fix round (#4101, F8): the prepared-text admin names the
character (not the sheet/crossing pk pair) and the approved field labels
("Vision (private)" / "Manifestation (room)") are admin-form labels, never
``verbose_name`` -- so no migration is generated for a cosmetic rename.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.admin import CharacterCrossingTextAdminForm
from world.magic.factories import CharacterCrossingTextFactory, CharacterSurgeTextFactory

CROSSING_CHANGELIST = reverse("admin:arxii_charactercrossingtext_changelist")
SURGE_CHANGELIST = reverse("admin:arxii_charactersurgetext_changelist")


class PreparedTextAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(
            username="prepared_text_staffer", is_staff=True, is_superuser=True
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_crossing_changelist_names_the_character(self):
        sheet = CharacterSheetFactory()
        CharacterCrossingTextFactory(character_sheet=sheet)
        response = self.client.get(CROSSING_CHANGELIST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Crossing text for {sheet.character.key}")

    def test_surge_changelist_names_the_character(self):
        sheet = CharacterSheetFactory()
        CharacterSurgeTextFactory(character_sheet=sheet)
        response = self.client.get(SURGE_CHANGELIST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Surge text for {sheet.character.key}")

    def test_crossing_changelist_does_not_add_a_query_per_row(self):
        # list_select_related covers character_sheet__character -- the query
        # count for the changelist must not grow with the row count.
        CharacterCrossingTextFactory(character_sheet=CharacterSheetFactory())
        with CaptureQueriesContext(connection) as one_row:
            self.client.get(CROSSING_CHANGELIST)

        for _ in range(3):
            CharacterCrossingTextFactory(character_sheet=CharacterSheetFactory())
        with CaptureQueriesContext(connection) as four_rows:
            self.client.get(CROSSING_CHANGELIST)

        self.assertEqual(len(one_row), len(four_rows))

    def test_crossing_form_uses_the_approved_field_labels(self):
        form = CharacterCrossingTextAdminForm()
        self.assertEqual(form.fields["character_sheet"].label, "Character")
        self.assertEqual(form.fields["vision_text"].label, "Vision (private)")
        self.assertEqual(form.fields["manifestation_text"].label, "Manifestation (room)")

    def test_crossing_change_page_renders_the_approved_field_labels(self):
        sheet = CharacterSheetFactory()
        text = CharacterCrossingTextFactory(character_sheet=sheet)
        url = reverse("admin:arxii_charactercrossingtext_change", args=[text.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # ">Character:<" (not just the substring "Character", which also
        # appears in the page title/breadcrumbs) pins this to the rendered
        # <label> text specifically.
        self.assertIn(">Character:<", body)
        self.assertIn("Vision (private)", body)
        self.assertIn("Manifestation (room)", body)
        # The old raw field-name labels are gone.
        self.assertNotIn(">Character sheet:<", body)
        self.assertNotIn("Vision text:", body)
        self.assertNotIn("Manifestation text:", body)

    def test_approved_labels_are_admin_form_only_no_migration(self):
        # verbose_name on the model field is untouched -- the rename lives
        # only in the ModelForm's Meta.labels (F8/F8b: no migration).
        model_meta = CharacterCrossingTextAdminForm.Meta.model._meta
        self.assertEqual(model_meta.get_field("character_sheet").verbose_name, "character sheet")
        self.assertEqual(model_meta.get_field("vision_text").verbose_name, "vision text")
