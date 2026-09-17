"""Organization admin applies its codex grants on every membership path (#3788).

The join service (``membership_services.join_organization``) already applies an
organization's ``OrganizationCodexGrant`` rows to a new member (#3780). This module
covers the two staff-facing paths that bypassed it: the Organization change form's
membership inline and the standalone ``OrganizationMembershipAdmin`` add form. It
also covers the new "Codex grants" inline on the Organization page itself, mixing
in ``GrantReachOnSaveMixin`` so a newly authored grant row reaches current members.
"""

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge, OrganizationCodexGrant
from world.codex.services import apply_organization_codex_grants
from world.roster.factories import RosterTenureFactory
from world.societies.admin import apply_grants_to_new_memberships
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationMembership

CODEX_GRANTS_VERBOSE_NAME = "Codex grants: what every member knows"


def _member_with_roster_entry(organization):
    """Build an active member of ``organization`` whose persona is roster-backed.

    ``OrganizationMembershipFactory``'s default ``PersonaFactory`` builds a bare
    ``CharacterSheet`` with no ``RosterEntry``; a member needs one to be reachable
    by the codex-knowledge machinery, so build the character through the roster
    stack instead (mirrors ``OrganizationGrantAdminTests`` in
    ``world/codex/tests/test_admin.py``).
    """
    tenure = RosterTenureFactory()
    roster_entry = tenure.roster_entry
    persona = roster_entry.character_sheet.primary_persona
    membership = OrganizationMembershipFactory(organization=organization, persona=persona)
    return membership, roster_entry


def _organization_form_data(response) -> dict:
    """Every field of the rendered Organization change form, as the browser would
    post it — including each existing inline row, not just its management form
    (the organization's auto-created rank ladder means every inline already has
    rows on a fresh organization, unlike a freshly created CodexEntry)."""
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
                value = [str(v) for v in value]
            data[form.add_prefix(name)] = value
    for fs in response.context["inline_admin_formsets"]:
        prefix = fs.formset.prefix
        data.setdefault(f"{prefix}-TOTAL_FORMS", "0")
        data.setdefault(f"{prefix}-INITIAL_FORMS", "0")
        data.setdefault(f"{prefix}-MIN_NUM_FORMS", "0")
        data.setdefault(f"{prefix}-MAX_NUM_FORMS", "1000")
    return data


class OrganizationChangeFormRendersCodexGrantsInlineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer", is_staff=True, is_superuser=True)
        cls.organization = OrganizationFactory()

    def test_change_form_shows_the_codex_grants_inline(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin:arxii_organization_change", args=[self.organization.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, CODEX_GRANTS_VERBOSE_NAME)


class ApplyGrantsToNewMembershipsTests(TestCase):
    """``apply_grants_to_new_memberships`` is the unit under test (#3788).

    ``OrganizationAdmin.save_related`` is a two-liner that calls
    ``super().save_related`` then this helper, so the helper is where the
    behaviour lives and is tested directly with a stub formset rather than
    driving the whole admin change-form machinery (mirrors
    ``apply_new_origin_rows`` in ``world/character_sheets/admin.py``, #3775).
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer", is_staff=True, is_superuser=True)
        cls.organization = OrganizationFactory()
        cls.first_entry = CodexEntryFactory(name="Inner Doctrine")
        cls.second_entry = CodexEntryFactory(name="Secret Handshake")
        OrganizationCodexGrant.objects.create(organization=cls.organization, entry=cls.first_entry)
        OrganizationCodexGrant.objects.create(organization=cls.organization, entry=cls.second_entry)

    def _request(self):
        request = RequestFactory().post("/")
        request.user = self.staff
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_new_membership_learns_the_organizations_grants(self):
        membership, roster_entry = _member_with_roster_entry(self.organization)

        class _Formset:
            model = OrganizationMembership
            new_objects = [membership]

        learned = apply_grants_to_new_memberships(self._request(), [_Formset()])

        self.assertEqual(learned, 2)
        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry).count(), 2
        )

    def test_a_second_call_learns_nothing_new(self):
        membership, roster_entry = _member_with_roster_entry(self.organization)

        class _Formset:
            model = OrganizationMembership
            new_objects = [membership]

        apply_grants_to_new_memberships(self._request(), [_Formset()])
        learned_again = apply_grants_to_new_memberships(self._request(), [_Formset()])

        self.assertEqual(learned_again, 0)
        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry).count(), 2
        )

    def test_a_formset_for_an_unrelated_model_is_ignored(self):
        class _Formset:
            model = OrganizationCodexGrant
            new_objects = []

        learned = apply_grants_to_new_memberships(self._request(), [_Formset()])

        self.assertEqual(learned, 0)


class OrganizationMembershipAdminGrantTests(TestCase):
    """A membership created through the standalone admin learns the org's grants."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer2", is_staff=True, is_superuser=True)
        cls.organization = OrganizationFactory()
        cls.entry = CodexEntryFactory(name="Inner Doctrine")
        OrganizationCodexGrant.objects.create(organization=cls.organization, entry=cls.entry)
        cls.tenure = RosterTenureFactory()
        cls.roster_entry = cls.tenure.roster_entry
        cls.persona = cls.roster_entry.character_sheet.primary_persona

    def setUp(self):
        self.client.force_login(self.staff)

    def test_creating_a_membership_applies_the_organizations_grants(self):
        response = self.client.post(
            reverse("admin:arxii_organizationmembership_add"),
            {"organization": self.organization.pk, "persona": self.persona.pk, "rank": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.roster_entry, entry=self.entry
            ).exists()
        )

    def test_editing_a_membership_does_not_apply_grants_again(self):
        """A membership built directly (bypassing the join service and admin
        creation) has learned nothing yet; an admin *edit* save must not teach it
        the organization's grants — only a *creation* save does (#3788)."""
        membership = OrganizationMembershipFactory(
            organization=self.organization, persona=self.persona
        )
        self.assertFalse(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.roster_entry, entry=self.entry
            ).exists()
        )
        response = self.client.post(
            reverse("admin:arxii_organizationmembership_change", args=[membership.pk]),
            {
                "organization": self.organization.pk,
                "persona": self.persona.pk,
                "rank": membership.rank_id or "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.roster_entry, entry=self.entry
            ).exists()
        )


class OrganizationCodexGrantInlineReachTests(TestCase):
    """Saving a new grant row on the Organization page reaches its current
    members, through ``GrantReachOnSaveMixin`` (#3775, mixed into
    ``OrganizationAdmin`` by #3788)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer3", is_staff=True, is_superuser=True)
        cls.organization = OrganizationFactory()
        cls.membership, cls.roster_entry = _member_with_roster_entry(cls.organization)
        cls.entry = CodexEntryFactory(name="Inner Doctrine")

    def setUp(self):
        self.client.force_login(self.staff)

    def test_saving_a_new_grant_inline_reaches_the_existing_member(self):
        url = reverse("admin:arxii_organization_change", args=[self.organization.pk])
        response = self.client.get(url)
        data = _organization_form_data(response)
        grants_fs = next(
            fs
            for fs in response.context["inline_admin_formsets"]
            if fs.formset.model is OrganizationCodexGrant
        )
        prefix = grants_fs.formset.prefix
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-0-entry": str(self.entry.pk),
            }
        )
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.roster_entry, entry=self.entry
            ).exists()
        )


class ApplyOrganizationCodexGrantsSanityTests(TestCase):
    """Guards the service-level assumption the admin helpers build on (#3780,
    already covered by the join path) so a regression there fails close to the
    admin tests that depend on it."""

    def test_apply_organization_codex_grants_is_idempotent(self):
        organization = OrganizationFactory()
        entry = CodexEntryFactory(name="Inner Doctrine")
        OrganizationCodexGrant.objects.create(organization=organization, entry=entry)
        membership, roster_entry = _member_with_roster_entry(organization)

        first = apply_organization_codex_grants(membership)
        second = apply_organization_codex_grants(membership)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry).count(), 1
        )
