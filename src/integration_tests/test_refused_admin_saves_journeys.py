"""Journeys for a refused save on a stock admin page (#4626).

Validating an admin form writes the posted values onto the row it edits, and every row
here is the one shared in-memory object the whole process reads (ADR-0008). A refused
save has to leave that object as the database holds it, for the page, the API, the game
and anything already holding the row. Each journey posts the change form (or the
changelist) through the test client, then reads the row back the way another request or
the game would: through the identity map, never with ``values_list``.

- An entry's filing that would list it under its own subject is refused, and the
  entry's edited summary is not served by the public codex API or the reloaded page.
- A Path saved with its name blanked keeps its stored description, and the corrected
  save then writes the new description.
- A character's known technique, loaded before staff open the page, still reads the
  stored technique after a refused save.
- A Path save that fails part way leaves the Path as stored.
- A list edit on the Tradition list with one bad row changes no row, in the list or the
  game; a list edit that fails after its rows were written leaves the game and the
  database agreeing.
- Evennia's own object page refuses a blank name and keeps the stored locks.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.urls import reverse
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.classes.factories import PathFactory
from world.classes.models import Path
from world.codex.factories import (
    CodexEntryFactory,
    CodexEntryFilingFactory,
    CodexSubjectFactory,
)
from world.codex.models import CodexEntry, CodexEntryFiling
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueFactory,
    TechniqueMoraleEffectFactory,
    TraditionFactory,
)
from world.magic.models import CharacterTechnique, Technique, Tradition


def _filled(bound_fields) -> dict[str, str | list[str]]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str | list[str]] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        elif isinstance(value, (list, tuple)):
            data[bound.html_name] = [str(item) for item in value]
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data


class RefusedAdminSaveCase(JourneyCase):
    """Staff signed in to the admin, with the change form's untouched post to hand."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def change_post(self, url: str) -> dict[str, str | list[str]]:
        """The change form at *url* as a browser would post it with nothing edited."""
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(_filled(formset.management_form))
            for form in formset.forms:
                data.update(_filled(form))
        return data


class ARefusedInlineLeavesTheEntryAsStored(RefusedAdminSaveCase):
    """The codex entry page refuses a filing under the entry's own subject."""

    def test_the_public_codex_and_the_reload_serve_the_stored_summary(self) -> None:
        entry = CodexEntryFactory(summary="What the archive says.", is_public=True)
        filing = CodexEntryFilingFactory(entry=entry, subject=CodexSubjectFactory())
        url = reverse("admin:arxii_codexentry_change", args=[entry.pk])
        data = self.change_post(url)
        data["summary"] = "A summary nobody saved."
        data["filings-0-subject"] = str(entry.subject_id)

        response = self.client.post(url, data)

        self.assertContains(response, "Cannot file an entry under its own canonical subject.")
        self.assertEqual(CodexEntry.objects.get(pk=entry.pk).summary, "What the archive says.")
        self.assertEqual(CodexEntryFiling.objects.get(pk=filing.pk).subject_id, filing.subject_id)
        served = self.api().get(f"/api/codex/entries/{entry.pk}/")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.json()["summary"], "What the archive says.")
        page = self.client.get(url)
        self.assertContains(page, "What the archive says.")
        self.assertNotContains(page, "A summary nobody saved.")


class AFieldErrorLeavesThePathAsStored(RefusedAdminSaveCase):
    """The Path page refuses a blank name while the description passes."""

    def setUp(self) -> None:
        super().setUp()
        self.path = PathFactory(name="Path of Embers", description="Walk where it burns.")
        self.url = reverse("admin:arxii_path_change", args=[self.path.pk])

    def test_the_game_reads_the_stored_description_and_the_corrected_save_writes(
        self,
    ) -> None:
        data = self.change_post(self.url)
        data["name"] = ""
        data["description"] = "A description nobody saved."

        refused = self.client.post(self.url, data)

        self.assertContains(refused, "This field is required.")
        self.assertEqual(Path.objects.get(pk=self.path.pk).description, "Walk where it burns.")
        self.assertContains(self.client.get(self.url), "Walk where it burns.")

        data["name"] = "Path of Embers"
        saved = self.client.post(self.url, data)

        self.assertEqual(saved.status_code, 302)
        self.assertEqual(
            Path.objects.get(pk=self.path.pk).description, "A description nobody saved."
        )

    def test_a_save_that_fails_part_way_leaves_the_path_as_stored(self) -> None:
        data = self.change_post(self.url)
        data["description"] = "A description the rollback took back."
        model_admin = admin.site._registry[Path]

        with (
            patch.object(model_admin, "save_related", side_effect=DatabaseError("lost")),
            self.assertRaises(DatabaseError),
        ):
            self.client.post(self.url, data)

        self.assertEqual(Path.objects.get(pk=self.path.pk).description, "Walk where it burns.")
        self.assertEqual(
            Path.objects.filter(pk=self.path.pk).values_list("description", flat=True).get(),
            "Walk where it burns.",
        )


class ARowAlreadyHeldReadsTheStoredTechnique(RefusedAdminSaveCase):
    """A row that held the technique before the refused save reads the stored one."""

    def test_a_known_technique_loaded_earlier_reads_the_stored_description(self) -> None:
        technique = TechniqueFactory(damage_profile=False, description="A low, cold hum.")
        TechniqueMoraleEffectFactory(technique=technique, base_morale=30)
        known = CharacterTechnique.objects.get(pk=CharacterTechniqueFactory(technique=technique).pk)
        self.assertEqual(known.technique.description, "A low, cold hum.")
        url = reverse("admin:arxii_technique_change", args=[technique.pk])
        data = self.change_post(url)
        data["description"] = "A description nobody saved."
        data["morale_effect-0-base_morale"] = "0"
        data["morale_effect-0-morale_intensity_multiplier"] = "0"
        data["morale_effect-0-morale_per_extra_sl"] = "0"

        response = self.client.post(url, data)

        self.assertContains(response, "This row removes no morale.")
        self.assertEqual(known.technique.description, "A low, cold hum.")
        self.assertEqual(known.technique.cached_morale_effect.base_morale, 30)
        self.assertEqual(Technique.objects.get(pk=technique.pk).description, "A low, cold hum.")


class ARefusedListEditChangesNoRow(RefusedAdminSaveCase):
    """The Tradition list refuses a bad sort order and keeps every row as stored."""

    def test_the_good_row_in_a_refused_list_edit_reads_as_stored(self) -> None:
        first = TraditionFactory(name="Ashen Choir", sort_order=1)
        second = TraditionFactory(name="Briar Hand", sort_order=2)
        url = reverse("admin:arxii_tradition_changelist")
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        formset = page.context["cl"].formset
        data = _filled(formset.management_form)
        for form in formset.forms:
            data.update(_filled(form))
        rows = {form.instance.pk: form.prefix for form in formset.forms}
        data[f"{rows[first.pk]}-sort_order"] = "not a number"
        data[f"{rows[second.pk]}-sort_order"] = "9"
        data["_save"] = "Save"

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a whole number.")
        self.assertEqual(Tradition.objects.get(pk=second.pk).sort_order, 2)
        self.assertEqual(Tradition.objects.get(pk=first.pk).sort_order, 1)

    def test_a_list_edit_that_fails_after_writing_leaves_the_game_and_database_agreeing(
        self,
    ) -> None:
        row = TraditionFactory(name="Cinder Wake", sort_order=4)
        url = reverse("admin:arxii_tradition_changelist")
        formset = self.client.get(url).context["cl"].formset
        data = _filled(formset.management_form)
        for form in formset.forms:
            data.update(_filled(form))
        prefix = next(form.prefix for form in formset.forms if form.instance.pk == row.pk)
        data[f"{prefix}-sort_order"] = "7"
        data["_save"] = "Save"
        model_admin = admin.site._registry[Tradition]

        with (
            patch.object(model_admin, "message_user", side_effect=DatabaseError("lost")),
            self.assertRaises(DatabaseError),
        ):
            self.client.post(url, data)

        stored = Tradition.objects.filter(pk=row.pk).values_list("sort_order", flat=True).get()
        self.assertEqual(Tradition.objects.get(pk=row.pk).sort_order, stored)
        self.assertEqual(stored, 4)


class EvenniasObjectPageKeepsTheStoredObject(RefusedAdminSaveCase):
    """Evennia's own admin for game objects is covered too."""

    def test_a_refused_rename_keeps_the_stored_locks(self) -> None:
        vestry = ObjectDBFactory(db_key="The Vestry", db_typeclass_path="typeclasses.rooms.Room")
        url = reverse("admin:objects_objectdb_change", args=[vestry.pk])
        data = self.change_post(url)
        stored_locks = vestry.db_lock_storage
        data["db_key"] = ""
        data["db_lock_storage"] = "get:false()"

        response = self.client.post(url, data)

        self.assertContains(response, "This field is required.")
        refetched = ObjectDB.objects.get(pk=vestry.pk)
        self.assertEqual(refetched.db_key, "The Vestry")
        self.assertEqual(refetched.db_lock_storage, stored_locks)
