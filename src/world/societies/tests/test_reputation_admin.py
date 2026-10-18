"""Staff edits of an organization's reputation go through the one writer (#4448)."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import PersonaFactory
from world.secrets.admin import SecretVictimInline
from world.secrets.factories import SecretFactory
from world.societies.constants import OrganizationReputationCause
from world.societies.factories import OrganizationFactory, OrganizationReputationFactory
from world.societies.models import OrganizationReputation, OrganizationReputationEvent


def _post_data(response, **overrides) -> dict:
    form = response.context["adminform"].form
    data = {}
    for name, field in form.fields.items():
        value = form.initial.get(name, field.initial)
        data[form.add_prefix(name)] = "" if value is None else value
    for formset in response.context["inline_admin_formsets"]:
        prefix = formset.formset.prefix
        data[f"{prefix}-TOTAL_FORMS"] = "0"
        data[f"{prefix}-INITIAL_FORMS"] = "0"
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
    data.update(overrides)
    return data


class OrganizationReputationAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="repstaff", is_staff=True, is_superuser=True)
        cls.persona = PersonaFactory()
        cls.org = OrganizationFactory()

    def setUp(self):
        self.client.force_login(self.staff)

    def test_an_edited_value_is_recorded_as_a_staff_adjustment(self):
        reputation = OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=100
        )
        url = reverse("admin:arxii_organizationreputation_change", args=[reputation.pk])
        data = _post_data(self.client.get(url), value="-300")
        response = self.client.post(url, data)
        assert response.status_code == 302, response.context and response.context["errors"]
        reputation = OrganizationReputation.objects.get(pk=reputation.pk)
        assert reputation.value == -300
        (event,) = OrganizationReputationEvent.objects.filter(reputation=reputation)
        assert event.cause == OrganizationReputationCause.STAFF_ADJUSTMENT
        assert event.amount == -400
        assert (event.tier_before, event.tier_after) == ("favored", "disliked")

    def test_a_saved_rows_persona_and_organization_cannot_be_changed(self):
        reputation = OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=100
        )
        other = OrganizationFactory()
        url = reverse("admin:arxii_organizationreputation_change", args=[reputation.pk])
        data = _post_data(
            self.client.get(url), value="-300", organization=str(other.pk), persona="999999"
        )
        assert self.client.post(url, data).status_code == 302
        reputation = OrganizationReputation.objects.get(pk=reputation.pk)
        assert (reputation.organization, reputation.persona, reputation.value) == (
            self.org,
            self.persona,
            -300,
        )
        assert not OrganizationReputation.objects.filter(organization=other).exists()

    def test_the_history_is_shown_read_only(self):
        reputation = OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=0
        )
        from world.societies.renown import bump_organization_reputation

        bump_organization_reputation(
            self.persona, self.org, -300, cause=OrganizationReputationCause.GANG_TURF
        )
        response = self.client.get(
            reverse("admin:arxii_organizationreputation_change", args=[reputation.pk])
        )
        self.assertContains(response, "Gang turf")
        self.assertContains(response, "-300")
        self.assertContains(response, "Changes (read only, newest first)")
        self.assertContains(response, "Unknown to Disliked (0 to -300)")

    def test_an_unchanged_value_records_nothing(self):
        reputation = OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=100
        )
        url = reverse("admin:arxii_organizationreputation_change", args=[reputation.pk])
        self.client.post(url, _post_data(self.client.get(url)))
        assert not OrganizationReputationEvent.objects.exists()

    def test_adding_a_row_records_its_starting_value(self):
        url = reverse("admin:arxii_organizationreputation_add")
        data = _post_data(
            self.client.get(url),
            persona=str(self.persona.pk),
            organization=str(self.org.pk),
            value="250",
        )
        response = self.client.post(url, data)
        assert response.status_code == 302
        reputation = OrganizationReputation.objects.get(persona=self.persona)
        assert reputation.value == 250
        (event,) = OrganizationReputationEvent.objects.filter(reputation=reputation)
        assert event.cause == OrganizationReputationCause.STAFF_ADJUSTMENT


class SecretVictimInlineTests(TestCase):
    def _formset(self, **row):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from world.secrets.models import Secret

        secret = SecretFactory()
        request = RequestFactory().get("/")
        request.user = AccountFactory(is_staff=True, is_superuser=True)
        inline = SecretVictimInline(Secret, site)
        formset_class = inline.get_formset(request, secret)
        data = {
            "victims-TOTAL_FORMS": "1",
            "victims-INITIAL_FORMS": "0",
            "victims-MIN_NUM_FORMS": "0",
            "victims-MAX_NUM_FORMS": "1000",
            "victims-0-organization": "",
            "victims-0-persona": "",
            **{f"victims-0-{key}": value for key, value in row.items()},
        }
        return formset_class(data, instance=secret, prefix="victims")

    def test_the_victims_help_is_drawn_on_the_page_not_only_in_a_tooltip(self):
        from django.urls import reverse

        client = self.client
        client.force_login(AccountFactory(is_staff=True, is_superuser=True))
        secret = SecretFactory()
        response = client.get(reverse("admin:arxii_secret_change", args=[secret.pk]))
        self.assertContains(response, "Set exactly one of organization or persona")
        self.assertContains(response, "per-victim size")
        self.assertContains(response, "Default victim severity")

    def test_the_inline_offers_no_severity(self):
        assert SecretVictimInline.fields == ["organization", "persona"]

    def test_an_organization_victim_is_accepted(self):
        assert self._formset(organization=str(OrganizationFactory().pk)).is_valid()

    def test_a_victim_with_both_or_neither_is_refused(self):
        both = self._formset(
            organization=str(OrganizationFactory().pk), persona=str(PersonaFactory().pk)
        )
        assert not both.is_valid()
        neither = self._formset(persona="", organization="")
        # An empty extra row is simply not submitted, so it saves nothing at all.
        assert neither.is_valid()
        assert not neither.save()
