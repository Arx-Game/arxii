"""The Spouses section of the Kinsperson admin page (#4232).

Staff add and end a marriage between two existing people where they are already
editing one of them; every row goes through the kinship services, so the union the
tree, the labels and the marital status read is the one the page writes.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.forms.widgets import MultiWidget, SelectMultiple
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.roster.admin import SpouseRow
from world.roster.constants import DefinitionTier, MaritalStatus, MembershipBasis
from world.roster.factories import FamilyFactory, ParentageEdgeFactory, UnionKindFactory
from world.roster.models import Kinsperson, Union
from world.roster.services import kinship
from world.roster.services.kinship import OMNISCIENT
from world.societies.factories import OrganizationFactory
from world.societies.houses.models import MarriagePact


def _posted_value(bound) -> object | None:
    """What the browser would post for one bound field; None for an unchecked checkbox."""
    value = bound.value()
    if value is None:
        # An empty multiple select posts nothing at all; an empty single input posts "".
        widget = bound.field.widget
        if isinstance(widget, RelatedFieldWidgetWrapper):  # the admin wraps related widgets
            widget = widget.widget
        return None if isinstance(widget, SelectMultiple) else ""
    if isinstance(value, bool):
        return "on" if value else None
    if isinstance(value, list):
        return [str(v) for v in value]
    return str(value)


def _errors(response) -> list:
    """Every form and formset error on a re-rendered change page, for a failing assertion."""
    if response.status_code == 302:  # a redirect carries no errors
        return []
    found = [response.context["adminform"].form.errors]
    for inline in response.context["inline_admin_formsets"]:
        found.append(inline.formset.non_form_errors())
        found.extend(form.errors for form in inline.formset.forms)
    return [e for e in found if e]


def _page_as_post(response) -> tuple[dict[str, object], str]:
    """The change page's form and inline formsets, as the browser would post them unchanged.

    Returns the data and the Spouses formset's prefix. Unchecked checkboxes are left out,
    as a browser leaves them out.
    """
    bound_fields = list(response.context["adminform"].form)
    spouse_prefix = ""
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        if formset.model is SpouseRow:
            spouse_prefix = formset.prefix
        bound_fields.extend(formset.management_form)
        for form in formset.initial_forms:
            bound_fields.extend(form)
    data: dict[str, object] = {}
    for bound in bound_fields:
        widget = bound.field.widget
        if isinstance(widget, MultiWidget):
            # A split date-time posts as two inputs, the way the admin renders it.
            for i, part in enumerate(widget.decompress(bound.value())):
                data[f"{bound.html_name}_{i}"] = "" if part is None else str(part)
            continue
        value = _posted_value(bound)
        if value is not None:
            data[bound.html_name] = value
    return data, spouse_prefix


class SpouseAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = AccountFactory(is_staff=True, is_superuser=True)
        cls.kind = UnionKindFactory(name="Marriage")
        cls.person = kinship.create_person(name="Rowan Ashby")
        cls.partner = kinship.create_person(name="Lisbet Crane")

    def _change_url(self) -> str:
        return reverse("admin:arxii_kinsperson_change", args=[self.person.pk])

    def _get_page(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self._change_url())
        self.assertEqual(response.status_code, 200)
        return response

    def _marry(self) -> Union:
        return kinship.record_union(
            kind=self.kind, members=[self.person, self.partner], started_at=timezone.now()
        )

    def test_the_change_page_lists_the_persons_marriages(self) -> None:
        self._marry()
        response = self._get_page()
        _, prefix = _page_as_post(response)
        self.assertContains(response, "Spouses")
        self.assertContains(response, "Lisbet Crane")
        self.assertContains(response, f'name="{prefix}-TOTAL_FORMS"')

    def test_a_new_row_records_a_union_the_tree_draws(self) -> None:
        family = FamilyFactory(name="Ashby")
        kinship.add_membership(kinsperson=self.person, family=family, basis=MembershipBasis.BORN)
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-0-id": "",
                f"{prefix}-0-kinsperson": str(self.person.pk),
                f"{prefix}-0-partner": str(self.partner.pk),
                f"{prefix}-0-kind": str(self.kind.pk),
                f"{prefix}-0-started_at": "2026-10-14 12:00:00",
                f"{prefix}-0-is_public_record": "on",
                f"{prefix}-0-is_true": "on",
            }
        )

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 302, _errors(response))
        union = Union.objects.get()
        self.assertEqual(union.kind, self.kind)
        self.assertEqual(set(union.members.all()), {self.person, self.partner})
        self.assertIsNotNone(union.started_at)
        self.assertIsNone(union.ended_at)
        tree = kinship.family_tree_for(family, OMNISCIENT)
        self.assertEqual([u["id"] for u in tree.unions], [union.pk])
        self.assertEqual(kinship.marital_status_of(self.person, OMNISCIENT), MaritalStatus.MARRIED)

    def test_the_new_row_defaults_to_the_wedlock_kind(self) -> None:
        response = self._get_page()
        spouse_formset = next(
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.model is SpouseRow
        )
        self.assertEqual(spouse_formset.empty_form.initial["kind"], self.kind.pk)

    def test_an_end_date_on_an_existing_row_ends_the_marriage(self) -> None:
        union = self._marry()
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data[f"{prefix}-0-ended_at"] = "2026-10-20 09:00:00"

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 302, _errors(response))
        union.refresh_from_db()
        self.assertIsNotNone(union.ended_at)
        self.assertEqual(kinship.marital_status_of(self.person, OMNISCIENT), MaritalStatus.DIVORCED)
        self.assertEqual(kinship.spouses_of(self.person, OMNISCIENT), [])

    def test_a_deleted_row_deletes_the_union(self) -> None:
        union = self._marry()
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data[f"{prefix}-0-DELETE"] = "on"

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 302, _errors(response))
        self.assertFalse(Union.objects.filter(pk=union.pk).exists())
        self.assertEqual(kinship.marital_status_of(self.person, OMNISCIENT), MaritalStatus.SINGLE)

    def test_a_row_with_a_pact_or_a_birth_cannot_be_deleted(self) -> None:
        union = self._marry()
        senior = OrganizationFactory(name="House Ashby")
        junior = OrganizationFactory(name="House Crane")
        MarriagePact.objects.create(union=union, senior_house=senior, junior_house=junior)
        ParentageEdgeFactory(parent=self.person, born_within_union=union)
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data[f"{prefix}-0-DELETE"] = "on"

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "a marriage pact and a recorded birth depends on it")
        self.assertTrue(Union.objects.filter(pk=union.pk).exists())

    def test_a_person_cannot_marry_themselves_or_a_current_spouse_twice(self) -> None:
        self._marry()
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "3",
                f"{prefix}-1-id": "",
                f"{prefix}-1-kinsperson": str(self.person.pk),
                f"{prefix}-1-partner": str(self.person.pk),
                f"{prefix}-1-kind": str(self.kind.pk),
                f"{prefix}-2-id": "",
                f"{prefix}-2-kinsperson": str(self.person.pk),
                f"{prefix}-2-partner": str(self.partner.pk),
                f"{prefix}-2-kind": str(self.kind.pk),
            }
        )

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A person cannot marry themselves.")
        self.assertContains(response, "They already share an open marriage.")
        self.assertEqual(Union.objects.count(), 1)

    def test_a_spouse_can_be_added_on_the_add_page(self) -> None:
        """The parent is unsaved while the row validates (the formset sets only its id,
        None); the row must not read the relation. Found by the mock-fidelity review."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:arxii_kinsperson_add"))
        self.assertEqual(response.status_code, 200)
        data, prefix = _page_as_post(response)
        data.update(
            {
                "name": "Newly Wed",
                "definition_tier": DefinitionTier.NAME_ONLY,
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-0-id": "",
                f"{prefix}-0-kinsperson": "",
                f"{prefix}-0-partner": str(self.partner.pk),
                f"{prefix}-0-kind": str(self.kind.pk),
                f"{prefix}-0-is_public_record": "on",
                f"{prefix}-0-is_true": "on",
            }
        )

        response = self.client.post(reverse("admin:arxii_kinsperson_add"), data)

        self.assertEqual(response.status_code, 302, _errors(response))
        newly = Kinsperson.objects.get(name="Newly Wed")
        union = Union.objects.get()
        self.assertEqual(set(union.members.all()), {newly, self.partner})
        self.assertEqual(kinship.marital_status_of(newly, OMNISCIENT), MaritalStatus.MARRIED)

    def test_the_partner_picker_finds_a_sheet_bound_person_by_character_name(self) -> None:
        """A player character's node has an empty name column; the autocomplete the
        picker uses must search the character's key (found on the live server)."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory(character__db_key="Marisol Vey")
        node = kinship.ensure_node_for_sheet(sheet)
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "arxii",
                "model_name": "union",
                "field_name": "members",
                "term": "Marisol",
            },
        )
        self.assertEqual(response.status_code, 200)
        ids = [int(row["id"]) for row in response.json()["results"]]
        self.assertEqual(ids, [node.pk])

    def test_a_person_a_marriage_still_binds_cannot_be_married_again(self) -> None:
        """Ruling on #4232: a marriage ends by death or dissolution before a new one."""
        self._marry()
        other = kinship.create_person(name="Tamsin Vole")
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "2",
                f"{prefix}-1-id": "",
                f"{prefix}-1-kinsperson": str(self.person.pk),
                f"{prefix}-1-partner": str(other.pk),
                f"{prefix}-1-kind": str(self.kind.pk),
            }
        )

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Rowan Ashby is already married; that marriage must end first."
        )
        self.assertEqual(Union.objects.count(), 1)

    def test_an_ended_marriage_does_not_block_a_new_one(self) -> None:
        old = self._marry()
        kinship.end_union(old, ended_at=timezone.now() - timedelta(days=1))
        response = self._get_page()
        data, prefix = _page_as_post(response)
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "2",
                f"{prefix}-1-id": "",
                f"{prefix}-1-kinsperson": str(self.person.pk),
                f"{prefix}-1-partner": str(self.partner.pk),
                f"{prefix}-1-kind": str(self.kind.pk),
                f"{prefix}-1-is_public_record": "on",
                f"{prefix}-1-is_true": "on",
            }
        )

        response = self.client.post(self._change_url(), data)

        self.assertEqual(response.status_code, 302, _errors(response))
        self.assertEqual(Union.objects.count(), 2)
        self.assertEqual(kinship.marital_status_of(self.person, OMNISCIENT), MaritalStatus.MARRIED)
