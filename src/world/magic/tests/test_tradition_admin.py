"""The Tradition admin page re-saves a tradition whose gift grants it did not touch (#4380)."""

from django.db.models import Model
from django.forms import ModelMultipleChoiceField
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.factories import (
    GiftFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import TraditionGiftGrant


def _form_data(response) -> dict:
    """Every field of the rendered Tradition change form, as the browser would post it,
    including each existing inline row and the blank extra row."""
    forms = [response.context["adminform"].form]
    for fs in response.context["inline_admin_formsets"]:
        forms.append(fs.formset.management_form)
        forms.extend(fs.formset.forms)
    data = {}
    for form in forms:
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "on" if value else ""
            elif isinstance(value, list):
                value = [str(v.pk) if isinstance(v, Model) else str(v) for v in value]
            elif isinstance(value, Model):
                value = str(value.pk)
            if value == "" and isinstance(field, ModelMultipleChoiceField):
                # A browser sends nothing at all for a multi-select with no pick.
                continue
            data[form.add_prefix(name)] = value
    return data


def _page_errors(response) -> str:
    """The admin page's error list when the save was refused; empty on a redirect."""
    if response.status_code != 200:
        return ""
    return str(response.context["errors"])


class TraditionChangeFormResaveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.tradition = TraditionFactory(name="Tide Readers", description="First wording.")
        cls.gift_a = GiftFactory(name="Tidecalling")
        cls.gift_b = GiftFactory(name="Stormbinding")
        cls.grant_a = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift_a)
        cls.grant_b = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift_b)

    def setUp(self) -> None:
        self.client.force_login(self.root)
        self.url = reverse("admin:arxii_tradition_change", args=[self.tradition.pk])

    def _resave_with_description(self, text: str):
        data = _form_data(self.client.get(self.url))
        data["description"] = text
        return self.client.post(self.url, data)

    def test_description_only_resave_keeps_both_grants(self) -> None:
        response = self._resave_with_description("Second wording.")

        self.assertEqual(response.status_code, 302, _page_errors(response))
        self.tradition.refresh_from_db()
        self.assertEqual(self.tradition.description, "Second wording.")
        self.assertEqual(
            sorted(
                TraditionGiftGrant.objects.filter(tradition=self.tradition).values_list(
                    "gift__name", flat=True
                )
            ),
            ["Stormbinding", "Tidecalling"],
        )

    def test_resave_with_special_techniques_on_each_grant(self) -> None:
        self.grant_a.special_techniques.add(TechniqueFactory(gift=self.gift_a, name="Ebb"))
        self.grant_b.special_techniques.add(TechniqueFactory(gift=self.gift_b, name="Gale"))

        response = self._resave_with_description("Third wording.")

        self.assertEqual(response.status_code, 302, _page_errors(response))
        self.assertEqual(self.grant_a.special_techniques.count(), 1)
        self.assertEqual(self.grant_b.special_techniques.count(), 1)


class TraditionAddThenEditFlowTests(TestCase):
    """The reporter's path: create the tradition and its grant rows on the add page,
    then reopen it and reword the description."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.gift_a = GiftFactory(name="Tidecalling")
        cls.gift_b = GiftFactory(name="Stormbinding")
        cls.ebb = TechniqueFactory(gift=cls.gift_a, name="Ebb")
        cls.flow = TechniqueFactory(gift=cls.gift_a, name="Flow")

    def setUp(self) -> None:
        self.client.force_login(self.root)

    def _add(self, rows: list[tuple[int, list[int]]]):
        data = _form_data(self.client.get(reverse("admin:arxii_tradition_add")))
        data.update({"name": "Tide Readers", "description": "First wording."})
        data["gift_grants-TOTAL_FORMS"] = str(len(rows))
        for i, (gift_pk, technique_pks) in enumerate(rows):
            data[f"gift_grants-{i}-gift"] = str(gift_pk)
            if technique_pks:
                data[f"gift_grants-{i}-special_techniques"] = [str(pk) for pk in technique_pks]
        return self.client.post(reverse("admin:arxii_tradition_add"), data)

    def test_two_gifts_then_reword(self) -> None:
        response = self._add([(self.gift_a.pk, [self.ebb.pk]), (self.gift_b.pk, [])])
        self.assertEqual(response.status_code, 302, _page_errors(response))
        tradition = TraditionGiftGrant.objects.get(gift=self.gift_a).tradition

        url = reverse("admin:arxii_tradition_change", args=[tradition.pk])
        data = _form_data(self.client.get(url))
        data["description"] = "Second wording."
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302, _page_errors(response))
        tradition.refresh_from_db()
        self.assertEqual(tradition.description, "Second wording.")

    def test_same_gift_on_two_rows_names_the_gift_and_says_where_techniques_go(self) -> None:
        """One row per technique is the natural misreading; the refusal has to correct it.

        Django's own line for this was "Please correct the duplicate data for
        gift." - the report that opened #4380.
        """
        response = self._add([(self.gift_a.pk, [self.ebb.pk]), (self.gift_a.pk, [self.flow.pk])])

        self.assertEqual(response.status_code, 200)
        expected = (
            "Gift 'Tidecalling' is already on another row. A tradition favors each gift "
            "on one row; pick every special technique it keeps from that gift there."
        )
        grants = next(
            fs.formset
            for fs in response.context["inline_admin_formsets"]
            if fs.formset.model is TraditionGiftGrant
        )
        self.assertEqual(list(grants.non_form_errors()), [expected])
        self.assertEqual(list(grants.forms[1].non_field_errors()), [expected])
        self.assertEqual(list(grants.forms[0].non_field_errors()), [])
        self.assertNotContains(response, "Please correct the duplicate data")
        self.assertFalse(TraditionGiftGrant.objects.exists())
